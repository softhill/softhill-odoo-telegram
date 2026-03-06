import json

from odoo import api, fields, models


class TelegramTool(models.Model):
    _name = "telegram.tool"
    _description = "Telegram Bot Tool"
    _order = "sequence, name"

    name = fields.Char(required=True, index=True)
    display_name_field = fields.Char(string="Display Name")
    description = fields.Text(required=True)
    category = fields.Selection(
        [
            ("read", "Read"),
            ("write", "Write"),
            ("github", "GitHub"),
            ("system", "System"),
        ],
        required=True,
        default="read",
    )
    input_schema = fields.Text(
        string="Input Schema (JSON)",
        required=True,
        default="{}",
    )
    method_name = fields.Char(
        required=True,
        help="Method name on telegram.ai.chat (e.g. _tool_search_odoo)",
    )
    permission_level = fields.Selection(
        [
            ("freela", "User"),
            ("dev", "Manager"),
            ("admin", "Admin"),
        ],
        default="freela",
        required=True,
        help="Minimum permission level (used when no profiles are configured)",
    )
    allowed_profile_ids = fields.Many2many(
        "telegram.user.profile",
        string="Allowed Profiles",
        help="User profiles that can use this tool. If empty, uses permission_level fallback.",
    )
    requires_confirmation = fields.Boolean(
        default=False,
        help="Require user confirmation before executing",
    )
    active = fields.Boolean(default=True)
    sequence = fields.Integer(default=10)

    # Stats (computed from telegram.message)
    usage_count = fields.Integer(
        compute="_compute_usage_count",
        string="Uses (30d)",
    )

    @api.depends("name")
    def _compute_usage_count(self):
        for tool in self:
            tool.usage_count = 0
            if not tool.name:
                continue
            query = """
                SELECT COUNT(*) FROM telegram_message
                WHERE tool_calls LIKE %s
                AND create_date >= NOW() - INTERVAL '30 days'
            """
            self.env.cr.execute(query, [f'%"{tool.name}"%'])
            result = self.env.cr.fetchone()
            tool.usage_count = result[0] if result else 0

    def to_openai_format(self):
        """Convert to OpenAI function calling format."""
        self.ensure_one()
        try:
            schema = json.loads(self.input_schema)
        except (json.JSONDecodeError, TypeError):
            schema = {"type": "object", "properties": {}}
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": schema,
            },
        }
