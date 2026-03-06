from odoo import fields, models


class TelegramMessage(models.Model):
    _name = "telegram.message"
    _description = "Telegram Message Log"
    _order = "create_date desc"

    telegram_message_id = fields.Char(index=True)
    chat_id = fields.Many2one("telegram.chat")
    user_id = fields.Many2one("res.users")
    direction = fields.Selection(
        [("in", "Recebida"), ("out", "Enviada")],
        required=True,
    )
    text = fields.Text()
    response = fields.Text()
    tool_calls = fields.Text(string="Tool Calls (JSON)")
    processing_time = fields.Float(string="Tempo (s)")
    ai_model = fields.Char()
    tokens_in = fields.Integer()
    tokens_out = fields.Integer()
    error = fields.Text()
