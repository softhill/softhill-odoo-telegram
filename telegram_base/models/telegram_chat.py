from odoo import fields, models


class TelegramChat(models.Model):
    _name = "telegram.chat"
    _description = "Telegram Chat"
    _order = "name"

    name = fields.Char(required=True)
    telegram_chat_id = fields.Char(
        string="Telegram Chat ID",
        required=True,
        index=True,
    )
    chat_type = fields.Selection(
        [
            ("dm", "DM"),
            ("socios", "Sócios"),
            ("equipe", "Equipe"),
            ("projeto", "Projeto"),
        ],
        default="equipe",
        required=True,
    )
    project_id = fields.Many2one("project.project", string="Projeto")
    permission_level = fields.Selection(
        [
            ("admin", "Admin"),
            ("dev", "Dev"),
            ("freela", "Freela"),
        ],
        default="dev",
        required=True,
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "telegram_chat_id_unique",
            "UNIQUE(telegram_chat_id)",
            "This Telegram chat is already registered.",
        ),
    ]
