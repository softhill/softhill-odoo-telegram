"""Bearer token authentication middleware for aiohttp.

Validates Authorization header against Odoo res.users.telegram_api_token.
Attaches UserContext to the request with channel='api'.
"""

import logging

from aiohttp import web

from bot_framework.odoo_client import OdooClient
from bot_framework.telegram_auth import UserContext

logger = logging.getLogger(__name__)


@web.middleware
async def api_auth_middleware(request: web.Request, handler):
    """Authenticate API requests via Bearer token."""
    # Health check and docs don't need auth
    if request.path in ("/health", "/api/docs"):
        return await handler(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return web.json_response(
            {"error": "Missing or invalid Authorization header"},
            status=401,
        )

    token = auth_header[7:]  # Strip "Bearer "
    odoo: OdooClient = request.app["odoo"]

    odoo_user = await odoo.find_user_by_api_token(token)
    if not odoo_user:
        return web.json_response(
            {"error": "Invalid API token"},
            status=401,
        )

    telegram_group = await odoo.get_user_telegram_group(odoo_user["id"])
    if not telegram_group:
        return web.json_response(
            {"error": "User has no Telegram permission group"},
            status=403,
        )

    # API users always have channel='api' and dm-level chat context
    request["user_ctx"] = UserContext(
        odoo_user_id=odoo_user["id"],
        odoo_user_name=odoo_user["name"],
        telegram_group=telegram_group,
        chat_permission=telegram_group,
        chat_type="dm",
        channel="api",
    )

    return await handler(request)
