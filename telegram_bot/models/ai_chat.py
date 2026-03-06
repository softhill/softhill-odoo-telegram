import json
import logging

import requests

from odoo import api, models

_logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5

SYSTEM_PROMPT = """Voce e o assistente operacional da Softhill, integrado ao Odoo.
Voce tem acesso direto ao sistema e pode consultar dados de vendas, compras, contatos,
projetos, horas, estoque e qualquer outro modulo do Odoo.

Responda de forma objetiva em portugues. Use os dados reais do sistema.
Quando o usuario pedir dados, use as ferramentas disponiveis para consultar o Odoo.

Permissao do usuario: {permission}
Nome do usuario: {user_name}
"""

ADMIN_CONTEXT = """
Voce tem acesso admin completo. Pode consultar dados de qualquer usuario,
aprovar mudancas, e executar acoes administrativas.
"""

DEV_CONTEXT = """
Voce tem acesso dev. Pode consultar projetos, tarefas e horas.
Nao pode aprovar mudancas ou ver dados de outros usuarios.
"""

FREELA_CONTEXT = """
Voce tem acesso freela. Pode ver apenas seus proprios projetos, tarefas e horas.
"""


class TelegramAIChat(models.AbstractModel):
    _name = "telegram.ai.chat"
    _description = "Telegram AI Chat Service"

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
    def _get_tools(self, permission):
        """Return OpenAI-format tool definitions."""
        tools = [
            {
                "type": "function",
                "function": {
                    "name": "search_odoo",
                    "description": (
                        "Busca registros em qualquer modelo Odoo. "
                        "Modelos comuns: sale.order, purchase.order, res.partner, "
                        "product.product, stock.picking, account.move, project.task, "
                        "account.analytic.line (horas). "
                        "Domain usa formato Odoo: [('field','operator','value')]."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {
                                "type": "string",
                                "description": "Nome tecnico do modelo Odoo",
                            },
                            "domain": {
                                "type": "array",
                                "description": "Filtros Odoo domain",
                            },
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "Campos a retornar",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Limite (padrao: 10)",
                            },
                            "order": {
                                "type": "string",
                                "description": "Ordenacao",
                            },
                        },
                        "required": ["model"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "count_odoo",
                    "description": "Conta registros em um modelo Odoo.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                            "domain": {"type": "array"},
                        },
                        "required": ["model"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "read_record",
                    "description": "Le um registro por ID.",
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                            "record_id": {"type": "integer"},
                            "fields": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                        },
                        "required": ["model", "record_id"],
                    },
                },
            },
            {
                "type": "function",
                "function": {
                    "name": "get_fields",
                    "description": (
                        "Descobre campos de um modelo Odoo. "
                        "Use antes de search_odoo se nao souber os campos."
                    ),
                    "parameters": {
                        "type": "object",
                        "properties": {
                            "model": {"type": "string"},
                        },
                        "required": ["model"],
                    },
                },
            },
        ]
        return tools

    @api.model
    def _execute_tool(self, name, args, user, permission):
        """Execute a tool call using the ORM directly."""
        method = getattr(self, f"_tool_{name}", None)
        if not method:
            return json.dumps({"error": f"Tool desconhecida: {name}"})
        try:
            result = method(args, user, permission)
            output = json.dumps(result, ensure_ascii=False, default=str)
            if len(output) > 6000:
                output = output[:6000] + "\n... (truncado)"
            return output
        except Exception as e:
            _logger.exception("Tool execution error: %s", name)
            return json.dumps({"error": str(e)})

    @api.model
    def _tool_search_odoo(self, args, user, permission):
        model_name = args["model"]
        domain = args.get("domain", [])
        field_list = args.get("fields")
        limit = args.get("limit", 10)
        order = args.get("order", "")

        # Permission filtering
        if permission == "freela" and model_name in (
            "project.task", "account.analytic.line"
        ):
            domain = domain + [("user_id", "=", user.id)]

        Model = self.env[model_name].sudo()
        kwargs = {"limit": limit}
        if order:
            kwargs["order"] = order
        records = Model.search_read(domain, field_list, **kwargs)
        return {"model": model_name, "count": len(records), "records": records}

    @api.model
    def _tool_count_odoo(self, args, user, permission):
        model_name = args["model"]
        domain = args.get("domain", [])
        count = self.env[model_name].sudo().search_count(domain)
        return {"model": model_name, "count": count}

    @api.model
    def _tool_read_record(self, args, user, permission):
        model_name = args["model"]
        record_id = args["record_id"]
        field_list = args.get("fields")
        records = self.env[model_name].sudo().search_read(
            [("id", "=", record_id)], field_list, limit=1
        )
        if not records:
            return {"error": f"{model_name} #{record_id} nao encontrado"}
        return {"record": records[0]}

    @api.model
    def _tool_get_fields(self, args, user, permission):
        model_name = args["model"]
        Model = self.env[model_name]
        fields_info = Model.fields_get(attributes=["string", "type", "relation"])
        simplified = [
            {
                "name": fname,
                "type": finfo["type"],
                "label": finfo["string"],
                "relation": finfo.get("relation", ""),
            }
            for fname, finfo in fields_info.items()
            if not fname.startswith("__")
        ]
        return {"model": model_name, "field_count": len(simplified), "fields": simplified}

    @api.model
    def chat(self, message, user, permission):
        """Send message to AI with function calling. Returns (response, tool_calls, usage)."""
        config = self._get_config()
        if not config["api_key"]:
            return "IA nao configurada. Configure em Configuracoes > Telegram.", [], {}

        perm_context = {
            "admin": ADMIN_CONTEXT,
            "dev": DEV_CONTEXT,
        }.get(permission, FREELA_CONTEXT)

        system = SYSTEM_PROMPT.format(
            permission=permission, user_name=user.name
        ) + perm_context

        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": message},
        ]
        tools = self._get_tools(permission)
        all_tool_calls = []

        headers = {
            "Authorization": f"Bearer {config['api_key']}",
            "Content-Type": "application/json",
        }

        for _round in range(MAX_TOOL_ROUNDS):
            payload = {
                "model": config["model"],
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 4096,
                "tools": tools,
                "tool_choice": "auto",
            }

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
                return "Erro ao comunicar com a IA.", [], {}

            choice = data["choices"][0]
            assistant_msg = choice["message"]
            usage = data.get("usage", {})
            usage["model"] = config["model"]

            if not assistant_msg.get("tool_calls"):
                return assistant_msg.get("content", ""), all_tool_calls, usage

            messages.append(assistant_msg)

            for tc in assistant_msg["tool_calls"]:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except json.JSONDecodeError:
                    func_args = {}

                _logger.info("Tool call: %s(%s)", func_name, func_args)
                all_tool_calls.append({"name": func_name, "args": func_args})

                result = self._execute_tool(func_name, func_args, user, permission)
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        return "Consulta muito complexa. Tente ser mais especifico.", all_tool_calls, usage
