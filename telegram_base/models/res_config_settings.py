from odoo import fields, models


class ResConfigSettings(models.TransientModel):
    _inherit = "res.config.settings"

    telegram_bot_token = fields.Char(
        string="Bot Token",
        config_parameter="telegram_base.bot_token",
    )
    telegram_webhook_secret = fields.Char(
        string="Webhook Secret",
        config_parameter="telegram_base.webhook_secret",
    )
    telegram_ai_provider = fields.Selection(
        [
            ("deepseek", "DeepSeek"),
            ("qwen", "Qwen"),
            ("openai", "OpenAI"),
        ],
        string="AI Provider",
        default="deepseek",
        config_parameter="telegram_base.ai_provider",
    )
    telegram_ai_api_key = fields.Char(
        string="AI API Key",
        config_parameter="telegram_base.ai_api_key",
    )
    telegram_ai_base_url = fields.Char(
        string="AI Base URL",
        config_parameter="telegram_base.ai_base_url",
        default="https://api.deepseek.com",
    )
    telegram_ai_model = fields.Char(
        string="AI Model",
        config_parameter="telegram_base.ai_model",
        default="deepseek-chat",
    )
