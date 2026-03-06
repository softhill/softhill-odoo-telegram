import json
import logging

import requests

from odoo import api, fields, models

_logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org/bot{token}/{method}"


class TelegramBot(models.AbstractModel):
    _name = "telegram.bot"
    _description = "Telegram Bot Service"

    @api.model
    def _get_token(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "telegram_base.bot_token", ""
        )

    @api.model
    def _api_call(self, method, **kwargs):
        token = self._get_token()
        if not token:
            _logger.error("Telegram bot token not configured")
            return {}
        url = TELEGRAM_API.format(token=token, method=method)
        try:
            resp = requests.post(url, json=kwargs, timeout=30)
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception:
            _logger.exception("Telegram API call failed: %s", method)
            return {}

    @api.model
    def send_message(self, chat_id, text, parse_mode="Markdown", **kwargs):
        return self._api_call(
            "sendMessage",
            chat_id=chat_id,
            text=text,
            parse_mode=parse_mode,
            **kwargs,
        )

    @api.model
    def send_document(self, chat_id, file_bytes, filename, caption="", parse_mode="Markdown"):
        """Send a document (file) to a Telegram chat."""
        token = self._get_token()
        if not token:
            _logger.error("Telegram bot token not configured")
            return {}
        url = TELEGRAM_API.format(token=token, method="sendDocument")
        data = {"chat_id": chat_id}
        if caption:
            data["caption"] = caption
            data["parse_mode"] = parse_mode
        files = {"document": (filename, file_bytes)}
        try:
            resp = requests.post(url, data=data, files=files, timeout=60)
            resp.raise_for_status()
            return resp.json().get("result", {})
        except Exception:
            _logger.exception("Telegram sendDocument failed")
            return {}

    @api.model
    def send_typing(self, chat_id):
        return self._api_call("sendChatAction", chat_id=chat_id, action="typing")

    @api.model
    def set_webhook(self, url):
        ICP = self.env["ir.config_parameter"].sudo()
        secret = ICP.get_param("telegram_base.webhook_secret", "")
        return self._api_call(
            "setWebhook",
            url=url,
            secret_token=secret,
            allowed_updates=["message", "callback_query"],
        )

    @api.model
    def delete_webhook(self):
        return self._api_call("deleteWebhook")

    @api.model
    def get_webhook_info(self):
        token = self._get_token()
        if not token:
            return {}
        url = TELEGRAM_API.format(token=token, method="getWebhookInfo")
        try:
            resp = requests.get(url, timeout=10)
            return resp.json().get("result", {})
        except Exception:
            return {}

    @api.model
    def get_me(self):
        return self._api_call("getMe")

    # --- Message processing ---

    @api.model
    def process_update(self, update):
        """Process a Telegram update (from webhook)."""
        callback = update.get("callback_query")
        if callback:
            self._handle_callback_query(callback)
            return

        message = update.get("message")
        if not message:
            return

        chat_tg_id = str(message["chat"]["id"])
        from_user = message.get("from", {})
        telegram_id = str(from_user.get("id", ""))
        text = message.get("text", "")

        if not text:
            return

        # Resolve Odoo user
        user = self.env["res.users"].sudo().search(
            [("telegram_id", "=", telegram_id)], limit=1
        )

        # Handle /start
        if text.startswith("/start"):
            self._handle_start(chat_tg_id, user, from_user)
            return

        # Handle /link (and legacy /vincular)
        if text.startswith("/link") or text.startswith("/vincular"):
            self._handle_link(chat_tg_id, telegram_id, text, from_user)
            return

        # Require linked user for all other messages
        if not user:
            self.send_message(
                chat_tg_id,
                "You are not linked to Odoo.\n"
                "Generate a code from your Odoo profile → Telegram tab, "
                "then use /link <code>.",
            )
            return

        # Check group chat: only respond if mentioned or replied
        tg_chat = message["chat"]
        if tg_chat["type"] != "private":
            if not self._should_respond_in_group(message):
                return
            # Auto-register group if not yet known
            self._ensure_chat_registered(tg_chat)

        # Resolve permission context and chat record
        chat_rec = self.env["telegram.chat"].sudo().search(
            [("telegram_chat_id", "=", chat_tg_id)], limit=1
        )
        # Auto-create chat record for DMs (needed for memory summary)
        if not chat_rec and tg_chat["type"] == "private":
            chat_rec = self.env["telegram.chat"].sudo().create({
                "name": f"DM - {from_user.get('first_name', '')} {from_user.get('last_name', '')}".strip(),
                "telegram_chat_id": str(chat_tg_id),
                "chat_type": "dm",
            })
        permission = self._resolve_permission(user, chat_tg_id)

        # Process with AI
        self.send_typing(chat_tg_id)
        self._process_ai_message(chat_tg_id, user, text, permission, chat_rec=chat_rec)

    @api.model
    def _get_bot_name(self):
        return self.env["ir.config_parameter"].sudo().get_param(
            "telegram_base.bot_display_name", "AI Assistant"
        )

    @api.model
    def _handle_start(self, chat_id, user, from_user):
        name = from_user.get("first_name", "")
        bot_name = self._get_bot_name()
        if user:
            self.send_message(
                chat_id,
                f"Hello, {user.name}! I'm {bot_name}.\n"
                "You can ask me anything about Odoo.",
            )
        else:
            self.send_message(
                chat_id,
                f"Hello, {name}! I'm {bot_name}.\n\n"
                "To connect your Odoo account:\n"
                "1. Open your Odoo profile → Telegram tab\n"
                "2. Click *Generate Link Code*\n"
                "3. Use /link <code> here",
            )

    @api.model
    def _handle_link(self, chat_id, telegram_id, text, from_user):
        parts = text.split(maxsplit=1)
        if len(parts) < 2:
            self.send_message(
                chat_id,
                "Usage: /link <code>\n\n"
                "To get your code, open your Odoo profile → Telegram tab "
                "→ click *Generate Link Code*.",
            )
            return

        code = parts[1].strip()

        # Check if already linked
        existing = self.env["res.users"].sudo().search(
            [("telegram_id", "=", telegram_id)], limit=1
        )
        if existing:
            self.send_message(
                chat_id, f"You are already linked as {existing.name}."
            )
            return

        # Verify code
        Users = self.env["res.users"]
        user, error = Users._verify_telegram_link_code(code)
        if error:
            self.send_message(chat_id, error)
            return

        if user.telegram_id:
            self.send_message(
                chat_id,
                "This Odoo account is already linked to another Telegram user.",
            )
            return

        # Link and clear the code
        user.sudo().write({
            "telegram_id": telegram_id,
            "telegram_link_code_hash": False,
            "telegram_link_code_expiry": False,
        })
        self.send_message(
            chat_id,
            f"Successfully linked! Welcome, {user.name}.\n"
            "You can now use the bot normally.",
        )
        _logger.info(
            "Linked Telegram %s to Odoo user %s (%s)",
            telegram_id, user.id, user.name,
        )

    @api.model
    def _ensure_chat_registered(self, tg_chat):
        """Auto-register a Telegram group/supergroup if not yet known."""
        chat_tg_id = str(tg_chat["id"])
        Chat = self.env["telegram.chat"].sudo()
        existing = Chat.search([("telegram_chat_id", "=", chat_tg_id)], limit=1)
        if existing:
            return existing

        chat_type = tg_chat.get("type", "group")
        name = tg_chat.get("title", f"Chat {chat_tg_id}")
        odoo_type = "group" if chat_type in ("group", "supergroup") else "team"

        chat = Chat.create({
            "name": name,
            "telegram_chat_id": chat_tg_id,
            "chat_type": odoo_type,
            "permission_level": "freela",  # safe default for new groups
        })
        _logger.info("Auto-registered Telegram group: %s (%s)", name, chat_tg_id)
        return chat

    @api.model
    def _should_respond_in_group(self, message):
        """Only respond in groups when mentioned or replied to."""
        bot_info = self.get_me()
        bot_username = bot_info.get("username", "")
        text = message.get("text", "")

        # Check mention
        for entity in message.get("entities", []):
            if entity["type"] == "mention":
                mention = text[entity["offset"]:entity["offset"] + entity["length"]]
                if mention == f"@{bot_username}":
                    return True

        # Check reply
        reply = message.get("reply_to_message")
        if reply and reply.get("from", {}).get("id") == bot_info.get("id"):
            return True

        return False

    @api.model
    def _resolve_permission(self, user, chat_tg_id):
        """Resolve effective permission for user + chat."""
        # User permission from groups
        if user.has_group("telegram_base.group_telegram_admin"):
            user_perm = "admin"
        elif user.has_group("telegram_base.group_telegram_dev"):
            user_perm = "dev"
        else:
            user_perm = "freela"

        # Chat permission
        chat = self.env["telegram.chat"].sudo().search(
            [("telegram_chat_id", "=", chat_tg_id)], limit=1
        )
        chat_perm = chat.permission_level if chat else user_perm

        # Effective = most restrictive
        levels = {"freela": 0, "dev": 1, "admin": 2}
        effective = min(levels.get(user_perm, 0), levels.get(chat_perm, 0))
        for name, level in levels.items():
            if level == effective:
                return name
        return "freela"

    @api.model
    def _handle_callback_query(self, callback):
        """Handle confirmation button presses."""
        callback_id = callback.get("id")
        data = callback.get("data", "")
        chat_tg_id = str(callback["message"]["chat"]["id"])

        # Answer callback to remove loading indicator
        self._api_call("answerCallbackQuery", callback_query_id=callback_id)

        if not data.startswith("confirm_") and not data.startswith("cancel_"):
            return

        parts = data.split("_", 1)
        action = parts[0]
        try:
            pending_id = int(parts[1])
        except (IndexError, ValueError):
            return

        pending = self.env["telegram.pending_action"].sudo().browse(pending_id)
        if not pending.exists() or pending.status != "pending":
            self.send_message(chat_tg_id, "Action already processed or expired.")
            return

        if action == "confirm":
            result = pending.execute_action()
            if "error" in result:
                self.send_message(chat_tg_id, f"Error: {result['error']}")
            else:
                self.send_message(
                    chat_tg_id,
                    f"Action confirmed: {pending.summary}\n"
                    f"Result: {json.dumps(result, ensure_ascii=False, default=str)}",
                )
        else:
            pending.cancel_action()
            self.send_message(chat_tg_id, "Action cancelled.")

    @api.model
    def send_chat_action(self, chat_id, action="typing"):
        """Send chat action (typing indicator) to a Telegram chat."""
        return self._api_call("sendChatAction", chat_id=chat_id, action=action)

    @api.model
    def edit_message(self, chat_id, message_id, text, parse_mode="Markdown"):
        """Edit an existing message."""
        return self._api_call(
            "editMessageText",
            chat_id=chat_id,
            message_id=message_id,
            text=text,
            parse_mode=parse_mode,
        )

    @api.model
    def _process_ai_message(self, chat_id, user, text, permission, chat_rec=None):
        """Process a message through the AI and send the response."""
        import time
        start = time.time()

        # Send initial status message
        status_msg = self.send_message(chat_id, "💭 Pensando...")
        status_msg_id = status_msg.get("message_id")

        def update_status(status_text):
            if status_msg_id:
                try:
                    self.edit_message(chat_id, status_msg_id, status_text, parse_mode="Markdown")
                except Exception:
                    pass

        ai = self.env["telegram.ai.chat"]
        error_msg = ""
        try:
            response, tool_calls, usage = ai.chat(
                text, user, permission, chat_id=chat_id, chat_rec=chat_rec,
                status_callback=update_status,
            )
        except Exception as e:
            _logger.exception("AI chat error")
            response = "Sorry, an error occurred while processing your message."
            tool_calls = []
            usage = {}
            error_msg = str(e)

        # Delete status message before sending final response
        if status_msg_id:
            try:
                self._api_call("deleteMessage", chat_id=chat_id, message_id=status_msg_id)
            except Exception:
                pass

        elapsed = time.time() - start

        # Log message
        self.env["telegram.message"].sudo().create({
            "user_id": user.id,
            "telegram_chat_id": str(chat_id),
            "direction": "in",
            "text": text,
            "response": response,
            "tool_calls": json.dumps(tool_calls) if tool_calls else False,
            "processing_time": elapsed,
            "ai_model": usage.get("model", ""),
            "tokens_in": usage.get("prompt_tokens", 0),
            "tokens_out": usage.get("completion_tokens", 0),
            "error": error_msg or False,
        })

        # Check if response contains confirmation requests
        if tool_calls:
            for tc in tool_calls:
                tc_result = tc.get("args", {})
                # The AI will mention confirmation in its response text

        # Check if there are pending confirmations to show buttons
        pending = self.env["telegram.pending_action"].sudo().search([
            ("user_id", "=", user.id),
            ("chat_id", "=", chat_id),
            ("status", "=", "pending"),
        ], limit=1, order="create_date desc")

        if pending:
            self.send_message(
                chat_id,
                response,
                reply_markup=json.dumps({
                    "inline_keyboard": [[
                        {"text": "Confirm", "callback_data": f"confirm_{pending.id}"},
                        {"text": "Cancel", "callback_data": f"cancel_{pending.id}"},
                    ]]
                }),
            )
        else:
            self.send_message(chat_id, response)

        # Trigger memory summarization (runs after response is sent)
        if chat_rec and not error_msg:
            try:
                self.env["telegram.ai.chat"].maybe_summarize(chat_rec)
            except Exception:
                _logger.exception("Memory summarization failed")
