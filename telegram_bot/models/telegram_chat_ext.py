from odoo import fields, models


class TelegramChatExt(models.Model):
    _inherit = "telegram.chat"

    allowed_tool_ids = fields.Many2many(
        "telegram.tool",
        string="Allowed Tools",
        help="If set, only these tools are available in this chat. "
             "Leave empty to allow all tools (based on permission level).",
    )
    custom_system_prompt = fields.Text(
        string="Custom System Prompt",
        help="Additional instructions for the AI in this chat. "
             "Injected into the system prompt for every message.",
    )
    memory_summary = fields.Text(
        string="Memory Summary",
        help="AI-generated summary of older conversations in this chat.",
    )
    memory_last_summarized_id = fields.Integer(
        string="Last Summarized Message ID",
        help="ID of the last telegram.message included in the summary.",
    )
