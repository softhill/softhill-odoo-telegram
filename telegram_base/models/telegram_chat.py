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
            ("dm", "Direct Message"),
            ("group", "Group"),
            ("team", "Team"),
            ("project", "Project"),
        ],
        default="team",
        required=True,
    )
    description = fields.Text(
        help="Internal notes about this chat (who participates, purpose, etc.)",
    )
    project_id = fields.Many2one("project.project", string="Project")
    permission_level = fields.Selection(
        [
            ("admin", "Admin"),
            ("dev", "Manager"),
            ("freela", "User"),
        ],
        default="dev",
        required=True,
        help="Maximum permission level for this chat. "
             "Effective permission = min(user level, chat level).",
    )
    profile_id = fields.Many2one(
        "telegram.user.profile",
        string="Chat Profile",
        help="If set, overrides permission_level for this chat.",
    )
    # allowed_tool_ids defined in telegram_bot module (inherits telegram.chat)
    active = fields.Boolean(default=True)

    _sql_constraints = [
        (
            "telegram_chat_id_unique",
            "UNIQUE(telegram_chat_id)",
            "This Telegram chat is already registered.",
        ),
    ]
