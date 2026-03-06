from odoo import fields, models


class TelegramChatExt(models.Model):
    _inherit = "telegram.chat"

    allowed_tool_ids = fields.Many2many(
        "telegram.tool",
        string="Allowed Tools",
        help="If set, only these tools are available in this chat. "
             "Leave empty to allow all tools (based on permission level).",
    )
