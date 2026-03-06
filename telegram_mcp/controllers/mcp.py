"""MCP (Model Context Protocol) server over SSE.

Implements the MCP Streamable HTTP transport specification.
IDEs like Claude Code and Cursor connect via SSE to use Odoo tools.
"""

import json
import logging
import uuid

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)

MCP_TOOLS = [
    {
        "name": "search_records",
        "description": (
            "Search records in any Odoo model. "
            "Common models: sale.order, purchase.order, res.partner, "
            "product.product, project.task, account.analytic.line."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string", "description": "Odoo model name"},
                "domain": {"type": "array", "description": "Odoo domain filter"},
                "fields": {"type": "array", "items": {"type": "string"}},
                "limit": {"type": "integer", "default": 10},
                "order": {"type": "string"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "count_records",
        "description": "Count records in an Odoo model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "domain": {"type": "array"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "read_record",
        "description": "Read a single record by ID.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
                "record_id": {"type": "integer"},
                "fields": {"type": "array", "items": {"type": "string"}},
            },
            "required": ["model", "record_id"],
        },
    },
    {
        "name": "list_models",
        "description": "List available Odoo models. Optionally filter by keyword.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Filter keyword"},
            },
        },
    },
    {
        "name": "get_model_fields",
        "description": "Get field definitions for an Odoo model.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "model": {"type": "string"},
            },
            "required": ["model"],
        },
    },
    {
        "name": "ask_ai",
        "description": "Ask the AI assistant a question about the Odoo system.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "question": {"type": "string"},
            },
            "required": ["question"],
        },
    },
]


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


def _execute_mcp_tool(name, arguments, user):
    """Execute an MCP tool and return the result."""
    env = request.env

    if name == "search_records":
        model = arguments["model"]
        domain = arguments.get("domain", [])
        fields_list = arguments.get("fields")
        limit = arguments.get("limit", 10)
        order = arguments.get("order", "")
        records = env[model].search_read(domain, fields_list, limit=limit, order=order)
        return json.dumps(
            {"model": model, "count": len(records), "records": records},
            ensure_ascii=False, default=str,
        )

    elif name == "count_records":
        model = arguments["model"]
        domain = arguments.get("domain", [])
        count = env[model].search_count(domain)
        return json.dumps({"model": model, "count": count})

    elif name == "read_record":
        model = arguments["model"]
        record_id = arguments["record_id"]
        fields_list = arguments.get("fields")
        records = env[model].search_read([("id", "=", record_id)], fields_list, limit=1)
        if not records:
            return json.dumps({"error": f"{model} #{record_id} not found"})
        return json.dumps(records[0], ensure_ascii=False, default=str)

    elif name == "list_models":
        query = arguments.get("query", "")
        domain = [("model", "ilike", query)] if query else []
        models = env["ir.model"].search_read(domain, ["model", "name"], order="model")
        return json.dumps({"models": models}, ensure_ascii=False, default=str)

    elif name == "get_model_fields":
        model = arguments["model"]
        Model = env[model]
        fields_info = Model.fields_get(attributes=["string", "type", "relation"])
        return json.dumps(
            {"model": model, "fields": fields_info},
            ensure_ascii=False, default=str,
        )

    elif name == "ask_ai":
        question = arguments["question"]
        permission = "admin" if user.has_group("telegram_base.group_telegram_admin") else "dev"
        response, _, _ = env["telegram.ai.chat"].chat(question, user, permission)
        return response

    return json.dumps({"error": f"Unknown tool: {name}"})


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
                    "name": "softhill-odoo-mcp",
                    "version": "1.0.0",
                },
            }

        elif method == "tools/list":
            return {"tools": MCP_TOOLS}

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
