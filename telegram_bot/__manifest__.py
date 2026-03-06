{
    "name": "Telegram Bot",
    "version": "18.0.1.0.0",
    "category": "Tools",
    "summary": "Telegram bot with AI chat and Odoo integration",
    "author": "Softhill",
    "website": "https://github.com/softhill/softhill-odoo-telegram",
    "license": "LGPL-3",
    "depends": ["telegram_base", "project"],
    "data": [
        "security/ir.model.access.csv",
        "views/telegram_message_views.xml",
        "views/telegram_bot_dashboard.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "installable": True,
    "application": True,
}
