import base64
import json
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """You are an AI assistant integrated with Odoo.
You have direct access to the system and can query and modify sales, purchases,
contacts, projects, timesheets, inventory and any other Odoo module data.
You can also query GitHub repositories.

You can generate PDF reports and send them as documents. When the user asks for
a report, document or formatted summary, use the generate_report tool with well-structured
HTML (tables, metrics, sections). First collect the data using other tools, then
build the HTML and generate the PDF.

Be concise and use real system data. When the user asks for data, use the available tools.
When asked to create or modify something, use the write tools.

User permission: {permission}
User name: {user_name}
"""

ADMIN_CONTEXT = """
You have full admin access. You can query and modify any data, create orders,
invoices, contacts, and perform administrative actions.
"""

DEV_CONTEXT = """
You have dev access. You can query and create records, but destructive actions
require confirmation. You can access GitHub repositories.
"""

FREELA_CONTEXT = """
You have freela access. You can only see your own projects, tasks and timesheets.
You cannot modify records.
"""

# Models that always require confirmation before write
CONFIRMATION_MODELS = {
    "sale.order", "purchase.order", "account.move",
    "stock.picking", "account.payment",
}

# Whitelisted methods for execute_action
ALLOWED_METHODS = {
    "action_confirm", "action_done", "action_cancel",
    "button_validate", "action_post", "action_draft",
    "action_assign", "action_set_done", "action_approve",
    "action_refuse", "action_reset",
}

# Models that should never be modified via bot
BLOCKED_MODELS = {
    "ir.model", "ir.model.access", "ir.rule", "ir.module.module",
    "ir.config_parameter", "res.groups", "ir.actions.server",
    "res.users", "ir.ui.view", "ir.ui.menu", "ir.attachment",
    "ir.mail.server", "fetchmail.server", "ir.cron",
    "base.automation", "ir.actions.act_window",
}

# Models that freela users are restricted from reading via generic tools.
# They can still use dedicated tools (sales_summary, etc.) which have
# their own per-tool permission gating.
FREELA_BLOCKED_MODELS = {
    "sale.order", "sale.order.line", "purchase.order", "purchase.order.line",
    "account.move", "account.move.line", "account.payment",
    "hr.employee", "hr.contract", "hr.payslip", "hr.expense",
    "crm.lead", "stock.picking", "stock.move",
    "res.users", "ir.config_parameter",
}

# Fields that should never be returned in generic search/read results
SENSITIVE_FIELDS = {
    "password", "password_crypt", "api_key", "token",
    "telegram_api_token", "secret", "credit_limit",
}


class TelegramAIChat(models.AbstractModel):
    _name = "telegram.ai.chat"
    _description = "Telegram AI Chat Service"

    @api.model
    def _resolve_user_profile(self, user):
        """Resolve the telegram user profile for a given user.

        Priority: 1) explicit telegram_profile_id on user, 2) profile
        matched via group_id (highest sequence first), 3) empty recordset
        (falls back to legacy permission_level).
        """
        if user.telegram_profile_id:
            return user.telegram_profile_id

        Profile = self.env["telegram.user.profile"].sudo()
        profiles = Profile.search(
            [("group_id", "!=", False)], order="sequence desc"
        )
        user_groups = user.groups_id
        for profile in profiles:
            if profile.group_id in user_groups:
                return profile
        return Profile.browse()  # empty recordset

    @staticmethod
    def _try_fix_json(raw):
        """Try to fix common LLM JSON issues (Python literals, etc.)."""
        import ast
        if not raw:
            return {}
        # Strategy 1: Python literal eval (handles True/False/None, single quotes, tuples)
        try:
            result = ast.literal_eval(raw)
            if isinstance(result, dict):
                return result
        except Exception:
            pass
        # Strategy 2: Replace common Python→JSON differences
        try:
            fixed = raw.replace("True", "true").replace("False", "false").replace("None", "null")
            return json.loads(fixed)
        except Exception:
            pass
        return {}

    @api.model
    def _get_config(self):
        ICP = self.env["ir.config_parameter"].sudo()
        return {
            "api_key": ICP.get_param("telegram_base.ai_api_key", ""),
            "base_url": ICP.get_param(
                "telegram_base.ai_base_url", "https://api.deepseek.com"
            ),
            "model": ICP.get_param("telegram_base.ai_model", "deepseek-chat"),
        }

    @api.model
    def _get_tools(self, permission, user_profile=None, chat_rec=None):
        """Return OpenAI-format tool definitions from telegram.tool records.

        Filtering layers (applied in order):
        1. Chat whitelist: if chat has allowed_tool_ids, only those tools
        2. Profile-based: if tool has allowed_profile_ids, check user profile
        3. Legacy fallback: compare permission levels
        """
        perm_levels = {"freela": 0, "dev": 1, "admin": 2}
        user_level = perm_levels.get(permission, 0)

        tools = self.env["telegram.tool"].sudo().search([("active", "=", True)])

        # Chat-level whitelist: restrict to allowed tools
        chat_allowed = chat_rec.allowed_tool_ids if chat_rec and chat_rec.allowed_tool_ids else None

        result = []
        for tool in tools:
            # Layer 1: chat whitelist
            if chat_allowed and tool not in chat_allowed:
                continue
            # Layer 2: profile-based access
            if tool.allowed_profile_ids and user_profile:
                if user_profile in tool.allowed_profile_ids:
                    result.append(tool.to_openai_format())
                continue
            # Layer 3: legacy permission level
            tool_level = perm_levels.get(tool.permission_level, 0)
            if user_level >= tool_level:
                result.append(tool.to_openai_format())
        return result

    @api.model
    def _execute_tool(self, name, args, user, permission, chat_id=None):
        """Execute a tool call using the ORM directly."""
        tool_rec = self.env["telegram.tool"].sudo().search(
            [("name", "=", name), ("active", "=", True)], limit=1
        )
        if not tool_rec:
            return json.dumps({"error": f"Unknown tool: {name}"})

        method = getattr(self, tool_rec.method_name, None)
        if not method:
            return json.dumps({"error": f"Method not implemented: {tool_rec.method_name}"})

        try:
            # Validate required parameters from tool schema
            try:
                schema = json.loads(tool_rec.input_schema) if tool_rec.input_schema else {}
            except (json.JSONDecodeError, TypeError):
                schema = {}
            required = schema.get("required", [])
            missing = [r for r in required if r not in args]
            if missing:
                return json.dumps({
                    "error": f"Missing required parameters: {', '.join(missing)}",
                    "hint": f"Required: {required}. Received: {list(args.keys())}",
                })

            if tool_rec.requires_confirmation and chat_id:
                if self._check_needs_confirmation(name, args):
                    return self._create_pending_action(name, args, user, chat_id)

            result = method(args, user, permission, chat_id=chat_id)
            output = json.dumps(result, ensure_ascii=False, default=str)
            if len(output) > 6000:
                output = output[:6000] + "\n... (truncated)"
            return output
        except Exception as e:
            _logger.exception("Tool execution error: %s", name)
            return json.dumps({"error": str(e)})

    @api.model
    def _check_needs_confirmation(self, tool_name, args):
        """Check if a specific call actually needs confirmation."""
        model = args.get("model", "")
        if tool_name in ("delete_record", "execute_action"):
            return True
        if tool_name in ("create_record", "update_record") and model in CONFIRMATION_MODELS:
            return True
        return False

    @api.model
    def _create_pending_action(self, tool_name, args, user, chat_id):
        """Create a pending action and return a confirmation prompt."""
        from datetime import timedelta
        action_map = {
            "create_record": "create",
            "update_record": "update",
            "delete_record": "delete",
            "execute_action": "execute",
        }
        action_type = action_map.get(tool_name, "execute")

        pending = self.env["telegram.pending_action"].sudo().create({
            "user_id": user.id,
            "chat_id": chat_id,
            "action_type": action_type,
            "model_name": args.get("model", ""),
            "record_id": args.get("record_id", 0),
            "action_data": json.dumps(args, default=str),
            "expires_at": fields.Datetime.now() + timedelta(minutes=5),
        })

        return json.dumps({
            "needs_confirmation": True,
            "confirmation_id": pending.id,
            "summary": pending.summary,
            "message": f"Action requires confirmation: {pending.summary}. The user will receive buttons to confirm or cancel.",
        })

    # ==========================================
    # READ TOOLS
    # ==========================================

    @api.model
    def _tool_search_odoo(self, args, user, permission, **kw):
        model_name = args["model"]
        domain = args.get("domain", [])
        field_list = args.get("fields")
        limit = args.get("limit", 10)
        order = args.get("order", "")

        if permission == "freela":
            if model_name in FREELA_BLOCKED_MODELS:
                return {"error": f"Access denied: use the dedicated tools for {model_name} data, or ask an admin."}
            if model_name in ("project.task", "account.analytic.line"):
                domain = domain + [("user_id", "=", user.id)]

        Model = self.env[model_name].sudo()
        kwargs = {"limit": limit}
        if order:
            kwargs["order"] = order

        # Filter out sensitive fields
        if field_list:
            field_list = [f for f in field_list if f not in SENSITIVE_FIELDS]

        records = Model.search_read(domain, field_list, **kwargs)

        # Remove sensitive fields from results if no field_list was specified
        if not args.get("fields"):
            for rec in records:
                for sf in SENSITIVE_FIELDS:
                    rec.pop(sf, None)

        return {"model": model_name, "count": len(records), "records": records}

    @api.model
    def _tool_count_odoo(self, args, user, permission, **kw):
        model_name = args["model"]
        domain = args.get("domain", [])
        if permission == "freela" and model_name in FREELA_BLOCKED_MODELS:
            return {"error": f"Access denied: use the dedicated tools for {model_name} data, or ask an admin."}
        count = self.env[model_name].sudo().search_count(domain)
        return {"model": model_name, "count": count}

    @api.model
    def _tool_read_record(self, args, user, permission, **kw):
        model_name = args["model"]
        record_id = args["record_id"]
        field_list = args.get("fields")
        if permission == "freela" and model_name in FREELA_BLOCKED_MODELS:
            return {"error": f"Access denied: use the dedicated tools for {model_name} data, or ask an admin."}

        if field_list:
            field_list = [f for f in field_list if f not in SENSITIVE_FIELDS]

        records = self.env[model_name].sudo().search_read(
            [("id", "=", record_id)], field_list, limit=1
        )
        if not records:
            return {"error": f"{model_name} #{record_id} not found"}

        if not args.get("fields"):
            for sf in SENSITIVE_FIELDS:
                records[0].pop(sf, None)

        return {"record": records[0]}

    @api.model
    def _tool_get_fields(self, args, user, permission, **kw):
        model_name = args["model"]
        Model = self.env[model_name]
        fields_info = Model.fields_get(
            attributes=["string", "type", "relation", "required", "readonly"]
        )
        simplified = [
            {
                "name": fname,
                "type": finfo["type"],
                "label": finfo["string"],
                "relation": finfo.get("relation", ""),
                "required": finfo.get("required", False),
                "readonly": finfo.get("readonly", False),
            }
            for fname, finfo in fields_info.items()
            if not fname.startswith("__")
        ]
        return {"model": model_name, "field_count": len(simplified), "fields": simplified}

    # ==========================================
    # WRITE TOOLS
    # ==========================================

    @api.model
    def _tool_create_record(self, args, user, permission, **kw):
        model_name = args["model"]
        values = args.get("values", {})

        if model_name in BLOCKED_MODELS:
            return {"error": f"Model {model_name} cannot be modified via bot"}

        record = self.env[model_name].sudo().create(values)
        return {"id": record.id, "display_name": record.display_name}

    @api.model
    def _tool_update_record(self, args, user, permission, **kw):
        model_name = args["model"]
        record_id = args["record_id"]
        values = args.get("values", {})

        if model_name in BLOCKED_MODELS:
            return {"error": f"Model {model_name} cannot be modified via bot"}

        record = self.env[model_name].sudo().browse(record_id)
        if not record.exists():
            return {"error": f"{model_name} #{record_id} not found"}

        record.write(values)
        return {"id": record.id, "display_name": record.display_name, "updated": True}

    @api.model
    def _tool_execute_action(self, args, user, permission, **kw):
        model_name = args["model"]
        record_id = args["record_id"]
        method = args["method"]

        if method not in ALLOWED_METHODS:
            return {
                "error": f"Method '{method}' not allowed. "
                f"Allowed: {', '.join(sorted(ALLOWED_METHODS))}"
            }

        record = self.env[model_name].sudo().browse(record_id)
        if not record.exists():
            return {"error": f"{model_name} #{record_id} not found"}

        getattr(record, method)()
        return {"executed": method, "id": record.id, "display_name": record.display_name}

    @api.model
    def _tool_delete_record(self, args, user, permission, **kw):
        model_name = args["model"]
        record_id = args["record_id"]

        if model_name in BLOCKED_MODELS:
            return {"error": f"Model {model_name} cannot be modified via bot"}

        record = self.env[model_name].sudo().browse(record_id)
        if not record.exists():
            return {"error": f"{model_name} #{record_id} not found"}

        name = record.display_name
        record.unlink()
        return {"deleted": True, "display_name": name}

    @api.model
    def _tool_post_message(self, args, user, permission, **kw):
        model_name = args["model"]
        record_id = args["record_id"]
        body = args["body"]
        msg_type = args.get("message_type", "note")

        record = self.env[model_name].sudo().browse(record_id)
        if not record.exists():
            return {"error": f"{model_name} #{record_id} not found"}

        subtype = "mail.mt_comment" if msg_type == "comment" else "mail.mt_note"
        record.message_post(
            body=body,
            message_type=msg_type if msg_type == "comment" else "notification",
            subtype_xmlid=subtype,
            author_id=user.partner_id.id,
        )
        return {"posted": True, "model": model_name, "record_id": record_id}

    # ==========================================
    # GITHUB TOOLS
    # ==========================================

    @api.model
    def _github_api(self, endpoint, params=None):
        """Call GitHub API with configured token."""
        ICP = self.env["ir.config_parameter"].sudo()
        token = ICP.get_param("telegram_base.github_token", "")
        if not token:
            return {"error": "GitHub token not configured. Set it in Settings > Telegram."}

        headers = {
            "Authorization": f"token {token}",
            "Accept": "application/vnd.github.v3+json",
        }
        url = f"https://api.github.com/{endpoint}"
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            return {"error": f"GitHub API: {e.response.status_code}"}
        except Exception as e:
            return {"error": f"GitHub API: {str(e)}"}

    @api.model
    def _get_github_org(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "telegram_base.github_org", ""
        )

    @api.model
    def _normalize_repo(self, repo):
        if "/" not in repo:
            return f"{self._get_github_org()}/{repo}"
        return repo

    @api.model
    def _tool_github_list_repos(self, args, user, permission, **kw):
        org = args.get("org", self._get_github_org())
        repo_type = args.get("type", "all")
        data = self._github_api(
            f"orgs/{org}/repos",
            {"type": repo_type, "per_page": 30, "sort": "updated"},
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {
            "org": org,
            "count": len(data),
            "repos": [
                {
                    "name": r["name"],
                    "private": r["private"],
                    "description": r.get("description", ""),
                    "updated_at": r["updated_at"],
                    "language": r.get("language", ""),
                }
                for r in data
            ],
        }

    @api.model
    def _tool_github_read_file(self, args, user, permission, **kw):
        repo = self._normalize_repo(args["repo"])
        path = args["path"]
        ref = args.get("ref", "main")
        data = self._github_api(f"repos/{repo}/contents/{path}", {"ref": ref})
        if isinstance(data, dict) and "error" in data:
            return data
        if isinstance(data, list):
            return {
                "type": "directory",
                "path": path,
                "files": [{"name": f["name"], "type": f["type"]} for f in data],
            }
        content = ""
        if data.get("content"):
            try:
                content = base64.b64decode(data["content"]).decode("utf-8", errors="replace")
            except Exception:
                content = "(binary file)"
        if len(content) > 10000:
            content = content[:10000] + "\n\n... (truncated)"
        return {"path": path, "size": data.get("size", 0), "content": content}

    @api.model
    def _tool_github_search_code(self, args, user, permission, **kw):
        query = args["query"]
        org = self._get_github_org()
        q = f"{query} org:{org}"
        if args.get("repo"):
            q = f"{query} repo:{self._normalize_repo(args['repo'])}"
        if args.get("extension"):
            q += f" extension:{args['extension']}"

        data = self._github_api("search/code", {"q": q, "per_page": 15})
        if isinstance(data, dict) and "error" in data:
            return data
        items = data.get("items", [])
        return {
            "total": data.get("total_count", 0),
            "results": [
                {"repo": i["repository"]["full_name"], "path": i["path"], "name": i["name"]}
                for i in items
            ],
        }

    @api.model
    def _tool_github_list_commits(self, args, user, permission, **kw):
        repo = self._normalize_repo(args["repo"])
        branch = args.get("branch", "main")
        limit = args.get("limit", 10)
        data = self._github_api(
            f"repos/{repo}/commits", {"sha": branch, "per_page": limit}
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {
            "repo": repo,
            "commits": [
                {
                    "sha": c["sha"][:8],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                }
                for c in data
            ],
        }

    @api.model
    def _tool_github_list_prs(self, args, user, permission, **kw):
        repo = self._normalize_repo(args["repo"])
        state = args.get("state", "open")
        data = self._github_api(
            f"repos/{repo}/pulls", {"state": state, "per_page": 15}
        )
        if isinstance(data, dict) and "error" in data:
            return data
        return {
            "repo": repo,
            "prs": [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "author": pr["user"]["login"],
                    "created_at": pr["created_at"],
                }
                for pr in data
            ],
        }

    # ==========================================
    # CHAT
    # ==========================================

    # Tool display names for status messages
    TOOL_LABELS = {
        "search_odoo": "🔍 Consultando dados...",
        "count_odoo": "🔢 Contando registros...",
        "read_odoo": "📖 Lendo registros...",
        "create_odoo": "✏️ Criando registro...",
        "write_odoo": "✏️ Atualizando registro...",
        "unlink_odoo": "🗑️ Removendo registro...",
        "execute_method": "⚙️ Executando ação...",
        "list_models": "📋 Listando modelos...",
        "model_fields": "📋 Verificando campos...",
        "search_github": "🐙 Consultando GitHub...",
        "list_github_prs": "🐙 Listando PRs...",
        "generate_report": "📊 Gerando relatório...",
    }

    @api.model
    def chat(self, message, user, permission, chat_id=None, chat_rec=None, status_callback=None):
        """Send message to AI with function calling. Returns (response, tool_calls, usage)."""
        config = self._get_config()
        if not config["api_key"]:
            return "AI not configured. Set it in Settings > Telegram.", [], {}

        def _notify(text):
            if status_callback:
                try:
                    status_callback(text)
                except Exception:
                    pass

        user_profile = self._resolve_user_profile(user)

        perm_context = {
            "admin": ADMIN_CONTEXT,
            "dev": DEV_CONTEXT,
        }.get(permission, FREELA_CONTEXT)

        profile_name = user_profile.name if user_profile else permission
        system = SYSTEM_PROMPT.format(
            permission=profile_name, user_name=user.name
        ) + perm_context

        # Add chat context if in a group
        if chat_rec and chat_rec.description:
            system += f"\nChat context: {chat_rec.description}\n"

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]
        tools = self._get_tools(permission, user_profile=user_profile, chat_rec=chat_rec)
        all_tool_calls = []

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        for _round in range(MAX_TOOL_ROUNDS):
            _notify("🤖 Pensando...")

            payload = {
                "model": config["model"],
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 8192,
            }
            if tools:
                payload["tools"] = tools
                payload["tool_choice"] = "auto"

            try:
                resp = requests.post(
                    f"{config['base_url']}/v1/chat/completions",
                    headers=headers,
                    json=payload,
                    timeout=60,
                )
                resp.raise_for_status()
                data = resp.json()
            except Exception:
                _logger.exception("AI API error")
                return "Error communicating with the AI provider.", [], {}

            choice = data["choices"][0]
            finish_reason = choice.get("finish_reason", "")
            assistant_msg = choice["message"]
            usage = data.get("usage", {})
            usage["model"] = config["model"]

            if finish_reason == "length":
                _logger.warning("AI response truncated (finish_reason=length)")
                return assistant_msg.get("content") or "Response was too long, please ask a simpler question.", all_tool_calls, usage

            if not assistant_msg.get("tool_calls"):
                _notify("✍️ Escrevendo resposta...")
                return assistant_msg.get("content", ""), all_tool_calls, usage

            messages.append(assistant_msg)

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                raw_args = tc["function"].get("arguments", "")
                try:
                    func_args = json.loads(raw_args) if raw_args else {}
                except json.JSONDecodeError as e:
                    _logger.warning(
                        "Bad tool args for %s: error=%s len=%d around_err=%s",
                        func_name, e, len(raw_args),
                        repr(raw_args[max(0, e.pos - 20):e.pos + 20]) if raw_args and hasattr(e, 'pos') else repr(raw_args[:80])
                    )
                    # Try to fix common LLM JSON issues
                    func_args = self._try_fix_json(raw_args)

                # Update status with tool label
                label = self.TOOL_LABELS.get(func_name, f"⚙️ Executando {func_name}...")
                _notify(label)

                _logger.info("Tool call: %s(%s)", func_name, func_args)
                all_tool_calls.append({"name": func_name, "args": func_args})

                result = self._execute_tool(
                    func_name, func_args, user, permission, chat_id=chat_id
                )
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        return "Query too complex. Please be more specific.", all_tool_calls, usage
