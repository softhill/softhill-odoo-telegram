import json

from odoo import api, fields, models

# Price per 1K tokens (input, output) in USD
MODEL_PRICING = {
    "deepseek-chat": (0.00014, 0.00028),
    "deepseek-reasoner": (0.00055, 0.00219),
    "qwen-plus": (0.0008, 0.002),
    "qwen-turbo": (0.0003, 0.0006),
    "gpt-4o-mini": (0.00015, 0.0006),
    "gpt-4o": (0.0025, 0.01),
}


class TelegramMessage(models.Model):
    _name = "telegram.message"
    _description = "Telegram Message Log"
    _order = "create_date desc"

    telegram_message_id = fields.Char(index=True)
    chat_id = fields.Many2one("telegram.chat")
    user_id = fields.Many2one("res.users", index=True)
    direction = fields.Selection(
        [("in", "Recebida"), ("out", "Enviada")],
        required=True,
    )
    text = fields.Text()
    response = fields.Text()
    tool_calls = fields.Text(string="Tool Calls (JSON)")
    processing_time = fields.Float(string="Tempo (s)")
    ai_model = fields.Char(index=True)
    tokens_in = fields.Integer()
    tokens_out = fields.Integer()
    error = fields.Text()

    # Analytics fields
    tokens_total = fields.Integer(
        compute="_compute_analytics", store=True,
    )
    estimated_cost = fields.Float(
        string="Custo (USD)",
        compute="_compute_analytics", store=True,
        digits=(10, 6),
    )
    tool_count = fields.Integer(
        string="Qtd Tools",
        compute="_compute_analytics", store=True,
    )
    has_error = fields.Boolean(
        compute="_compute_analytics", store=True,
    )

    @api.depends("tokens_in", "tokens_out", "ai_model", "tool_calls", "error")
    def _compute_analytics(self):
        for rec in self:
            rec.tokens_total = (rec.tokens_in or 0) + (rec.tokens_out or 0)
            rec.has_error = bool(rec.error)

            pricing = MODEL_PRICING.get(rec.ai_model, (0.001, 0.002))
            rec.estimated_cost = (
                (rec.tokens_in or 0) / 1000 * pricing[0]
                + (rec.tokens_out or 0) / 1000 * pricing[1]
            )

            count = 0
            if rec.tool_calls:
                try:
                    calls = json.loads(rec.tool_calls)
                    count = len(calls) if isinstance(calls, list) else 0
                except (json.JSONDecodeError, TypeError):
                    pass
            rec.tool_count = count
