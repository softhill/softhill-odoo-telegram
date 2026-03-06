from odoo import fields, models


class TelegramChat(models.Model):
    _name = "telegram.chat"
    _description = "Telegram Chat Mapping"
    _order = "name"

    name = fields.Char(required=True)
    telegram_chat_id = fields.Char(
        string="Chat ID",
        required=True,
        index=True,
        help="Telegram chat ID (negative for groups).",
    )
    chat_type = fields.Selection(
        [
            ("dm", "Direct Message"),
            ("socios", "Partners Group"),
            ("equipe", "Team Group"),
            ("projeto", "Project Group"),
        ],
        required=True,
        default="dm",
    )
    project_id = fields.Many2one(
        "project.project",
        string="Project",
        help="Required when chat_type is 'projeto'.",
    )
    permission_level = fields.Selection(
        [
            ("admin", "Admin - Full access"),
            ("dev", "Dev - Projects and code"),
            ("freela", "Freela - Assigned tasks only"),
        ],
        required=True,
        default="dev",
    )
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "telegram_chat_id_unique",
            "UNIQUE(telegram_chat_id)",
            "This Telegram chat is already registered.",
        ),
    ]
