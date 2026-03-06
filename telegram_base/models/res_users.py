import secrets

from odoo import api, fields, models


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
