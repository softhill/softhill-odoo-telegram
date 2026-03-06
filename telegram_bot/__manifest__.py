{
    "name": "Telegram Bot",
    "version": "18.0.2.0.0",
    "category": "Tools",
    "summary": "Telegram bot with AI chat, function calling, and full Odoo integration",
    "author": "Softhill",
    "website": "https://github.com/softhill/softhill-odoo-telegram",
    "license": "LGPL-3",
    "depends": ["telegram_base", "project", "mail"],
    "data": [
        "security/ir.model.access.csv",
        "data/telegram_tools_data.xml",
        "data/telegram_tools_core_data.xml",
        "views/telegram_message_views.xml",
        "views/telegram_bot_dashboard.xml",
        "views/telegram_tool_views.xml",
        "views/telegram_analytics_views.xml",
    ],
    "external_dependencies": {
        "python": ["requests"],
    },
    "installable": True,
    "application": True,
}
