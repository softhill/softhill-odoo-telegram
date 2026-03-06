import hashlib
import secrets
from datetime import timedelta

from odoo import api, fields, models

LINK_CODE_EXPIRY_MINUTES = 10


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_id = fields.Char(
        string="Telegram ID",
        copy=False,
        index=True,
    )
    telegram_api_token = fields.Char(
        string="Telegram API Token",
        copy=False,
        groups="telegram_base.group_telegram_admin",
    )
    telegram_profile_id = fields.Many2one(
        "telegram.user.profile",
        string="Telegram Profile",
        help="User profile for Telegram bot. If not set, determined from Odoo groups.",
    )
    telegram_link_code_hash = fields.Char(
        string="Link Code Hash",
        copy=False,
        groups="telegram_base.group_telegram_admin",
    )
    telegram_link_code_expiry = fields.Datetime(
        string="Link Code Expiry",
        copy=False,
        groups="telegram_base.group_telegram_admin",
    )

    _sql_constraints = [
        (
            "telegram_id_unique",
            "UNIQUE(telegram_id)",
            "This Telegram ID is already linked to another user.",
        ),
    ]

    def action_generate_telegram_token(self):
        self.ensure_one()
        self.telegram_api_token = secrets.token_urlsafe(32)

    def action_revoke_telegram_token(self):
        self.ensure_one()
        self.telegram_api_token = False

    def action_generate_telegram_link_code(self):
        """Generate a 6-digit code for Telegram account linking."""
        self.ensure_one()
        code = f"{secrets.randbelow(900000) + 100000}"
        self.sudo().write({
            "telegram_link_code_hash": hashlib.sha256(code.encode()).hexdigest(),
            "telegram_link_code_expiry": fields.Datetime.now() + timedelta(
                minutes=LINK_CODE_EXPIRY_MINUTES
            ),
        })
        return {
            "type": "ir.actions.client",
            "tag": "display_notification",
            "params": {
                "title": "Telegram Link Code",
                "message": f"Your code: {code}\n"
                           f"Use /link {code} in Telegram within "
                           f"{LINK_CODE_EXPIRY_MINUTES} minutes.",
                "type": "info",
                "sticky": True,
            },
        }

    def action_unlink_telegram(self):
        """Remove Telegram account link."""
        self.ensure_one()
        self.sudo().write({
            "telegram_id": False,
            "telegram_link_code_hash": False,
            "telegram_link_code_expiry": False,
        })

    @api.model
    def _verify_telegram_link_code(self, code):
        """Verify a link code and return the matching user or error message.

        Searches by SHA-256 hash of the code, so no user enumeration is possible.
        Security: 1/900,000 chance per guess, 10-min expiry, single-use (cleared on success).

        Returns (user_record, None) on success or (None, error_string) on failure.
        """
        code_hash = hashlib.sha256(code.strip().encode()).hexdigest()
        user = self.sudo().search([
            ("telegram_link_code_hash", "=", code_hash),
            ("telegram_link_code_expiry", ">=", fields.Datetime.now()),
        ], limit=1)

        if not user:
            return None, "Invalid or expired code. Generate a new one from your Odoo profile."

        return user, None
