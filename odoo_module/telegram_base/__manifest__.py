{
    "name": "Telegram Base",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Base module for Telegram bot integration with Odoo",
    "description": """
        Provides base fields and models for integrating Telegram bots with Odoo:
        - telegram_id and api_token on res.users
        - telegram.chat model for mapping Telegram chats to permissions
        - Security groups: Telegram Admin, Telegram Dev, Telegram Freela
    """,
    "author": "Softhill",
    "website": "https://github.com/softhill/softhill-odoo-telegram",
    "license": "LGPL-3",
    "depends": ["base", "project"],
    "data": [
        "security/telegram_security.xml",
        "security/ir.model.access.csv",
        "views/res_users_views.xml",
        "views/telegram_chat_views.xml",
    ],
    "installable": True,
    "application": False,
}
