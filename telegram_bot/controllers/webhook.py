import hashlib
import hmac
import json
import logging

from odoo import http
from odoo.http import request

_logger = logging.getLogger(__name__)


class TelegramWebhook(http.Controller):

    @http.route(
        "/telegram/webhook",
        type="json",
        auth="none",
        methods=["POST"],
        csrf=False,
    )
    def webhook(self):
        # Validate secret token
        ICP = request.env["ir.config_parameter"].sudo()
        secret = ICP.get_param("telegram_base.webhook_secret", "")
        if secret:
            header_secret = request.httprequest.headers.get(
                "X-Telegram-Bot-Api-Secret-Token", ""
            )
            if not hmac.compare_digest(secret, header_secret):
                _logger.warning("Invalid webhook secret")
                return {"ok": False}

        try:
            update = request.get_json_data()
        except Exception:
            update = json.loads(request.httprequest.get_data(as_text=True))

        _logger.debug("Telegram update: %s", update.get("update_id"))

        try:
            request.env["telegram.bot"].sudo().process_update(update)
        except Exception:
            _logger.exception("Error processing Telegram update")

        return {"ok": True}

    @http.route(
        "/telegram/health",
        type="http",
        auth="none",
        methods=["GET"],
        csrf=False,
    )
    def health(self):
        ICP = request.env["ir.config_parameter"].sudo()
        token = ICP.get_param("telegram_base.bot_token", "")
        return json.dumps({
            "status": "ok" if token else "not_configured",
            "bot_configured": bool(token),
        })
