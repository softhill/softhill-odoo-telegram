import secrets

from odoo import api, fields, models


class ResUsers(models.Model):
    _inherit = "res.users"

    telegram_id = fields.Char(
        string="Telegram ID",
        index=True,
        copy=False,
        help="Telegram user ID linked to this Odoo user.",
    )
    telegram_api_token = fields.Char(
        string="API Token",
        copy=False,
        readonly=True,
        help="Bearer token for REST API authentication.",
    )

    _sql_constraints = [
        (
            "telegram_id_unique",
            "UNIQUE(telegram_id)",
            "This Telegram ID is already linked to another user.",
        ),
        (
            "telegram_api_token_unique",
            "UNIQUE(telegram_api_token)",
            "API token must be unique.",
        ),
    ]

    def action_generate_api_token(self):
        for user in self:
            user.telegram_api_token = secrets.token_urlsafe(32)

    def action_revoke_api_token(self):
        for user in self:
            user.telegram_api_token = False

    @api.model
    def _find_by_telegram_id(self, telegram_id):
        """Find user by Telegram ID. Returns recordset (empty if not found)."""
        return self.search([("telegram_id", "=", str(telegram_id))], limit=1)

    @api.model
    def _find_by_api_token(self, token):
        """Find user by API token. Returns recordset (empty if not found)."""
        if not token:
            return self.browse()
        return self.search([("telegram_api_token", "=", token)], limit=1)

    def _get_telegram_group(self):
        """Return the highest telegram permission group for this user."""
        self.ensure_one()
        if self.has_group("telegram_base.group_telegram_admin"):
            return "admin"
        if self.has_group("telegram_base.group_telegram_dev"):
            return "dev"
        if self.has_group("telegram_base.group_telegram_freela"):
            return "freela"
        return None
