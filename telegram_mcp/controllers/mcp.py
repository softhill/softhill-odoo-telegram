"""MCP (Model Context Protocol) server over Streamable HTTP.

Implements the MCP Streamable HTTP transport specification.
IDEs like Claude Code and Cursor connect to use Odoo tools.
Tools are loaded dynamically from telegram.tool records.
"""

import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def _authenticate_mcp():
    """Authenticate via Bearer token, return user or None."""
    auth = request.httprequest.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return None
    token = auth[7:]
    user = request.env["res.users"].sudo().search(
        [("telegram_api_token", "=", token)], limit=1
    )
    if user:
        request.update_env(user=user.id)
    return user


def _get_mcp_tools(user):
    """Get tool list filtered by user permission in MCP format."""
    # Resolve permission level
    if user.has_group("telegram_base.group_telegram_admin"):
        permission = "admin"
    elif user.has_group("telegram_base.group_telegram_dev"):
        permission = "dev"
    else:
        permission = "freela"

    levels = {"freela": 0, "dev": 1, "admin": 2}
    user_level = levels.get(permission, 0)

    tools = request.env["telegram.tool"].sudo().search([("active", "=", True)])
    result = []
    for tool in tools:
        # Filter by permission level
        tool_level = levels.get(tool.permission_level, 0)
        if tool_level > user_level:
            continue
        try:
            schema = json.loads(tool.input_schema)
        except (json.JSONDecodeError, TypeError):
            schema = {"type": "object", "properties": {}}
        result.append({
            "name": tool.name,
            "description": tool.description,
            "inputSchema": schema,
        })
    return result


def _execute_mcp_tool(name, arguments, user):
    """Execute an MCP tool via the AI chat service."""
    env = request.env

    # Resolve permission
    if user.has_group("telegram_base.group_telegram_admin"):
        permission = "admin"
    elif user.has_group("telegram_base.group_telegram_dev"):
        permission = "dev"
    else:
        permission = "freela"

    ai_chat = env["telegram.ai.chat"]
    result = ai_chat._execute_tool(name, arguments, user, permission)
    return result


class MCPController(http.Controller):

    @http.route("/mcp", type="http", auth="none", methods=["POST"], csrf=False)
    def mcp_endpoint(self):
        """MCP Streamable HTTP transport endpoint."""
        user = _authenticate_mcp()
        if not user:
            return Response(
                json.dumps({"jsonrpc": "2.0", "error": {"code": -32000, "message": "Unauthorized"}}),
                status=401,
                content_type="application/json",
            )

        try:
            body = json.loads(request.httprequest.get_data(as_text=True))
        except json.JSONDecodeError:
            return Response(
                json.dumps({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}}),
                status=400,
                content_type="application/json",
            )

        method = body.get("method")
        req_id = body.get("id")
        params = body.get("params", {})

        result = self._handle_mcp_method(method, params, user)

        response = {"jsonrpc": "2.0", "id": req_id}
        if "error" in result:
            response["error"] = result["error"]
        else:
            response["result"] = result

        return Response(
            json.dumps(response, ensure_ascii=False, default=str),
            content_type="application/json",
        )

    def _handle_mcp_method(self, method, params, user):
        if method == "initialize":
            return {
                "protocolVersion": "2025-03-26",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": "odoo-telegram-mcp",
                    "version": "2.0.0",
                },
            }

        elif method == "tools/list":
            return {"tools": _get_mcp_tools(user)}

        elif method == "tools/call":
            tool_name = params.get("name")
            arguments = params.get("arguments", {})
            try:
                result_text = _execute_mcp_tool(tool_name, arguments, user)
                return {
                    "content": [{"type": "text", "text": result_text}],
                }
            except Exception as e:
                _logger.exception("MCP tool error: %s", tool_name)
                return {
                    "content": [{"type": "text", "text": f"Error: {e}"}],
                    "isError": True,
                }

        elif method == "notifications/initialized":
            return {}

        return {"error": {"code": -32601, "message": f"Method not found: {method}"}}
