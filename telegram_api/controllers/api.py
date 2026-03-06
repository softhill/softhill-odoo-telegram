import json
import logging

from odoo import http
from odoo.http import request, Response

_logger = logging.getLogger(__name__)


def _json_response(data, status=200):
    return Response(
        json.dumps(data, ensure_ascii=False, default=str),
        status=status,
        content_type="application/json",
    )


def _authenticate(func):
    """Decorator to authenticate API requests via Bearer token."""
    def wrapper(self, *args, **kwargs):
        auth = request.httprequest.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return _json_response({"error": "Missing or invalid Authorization header"}, 401)

        token = auth[7:]
        user = request.env["res.users"].sudo().search(
            [("telegram_api_token", "=", token)], limit=1
        )
        if not user:
            return _json_response({"error": "Invalid token"}, 401)

        request.update_env(user=user.id)
        request._api_user = user
        return func(self, *args, **kwargs)
    return wrapper


class TelegramAPI(http.Controller):

    @http.route("/api/v1/health", type="http", auth="none", methods=["GET"], csrf=False)
    def health(self):
        return _json_response({"status": "ok"})

    @http.route("/api/v1/chat", type="http", auth="none", methods=["POST"], csrf=False)
    @_authenticate
    def chat(self):
        try:
            data = json.loads(request.httprequest.get_data(as_text=True))
        except (json.JSONDecodeError, TypeError):
            return _json_response({"error": "Invalid JSON body"}, 400)
        message = data.get("message", "")
        if not message:
            return _json_response({"error": "message is required"}, 400)

        user = request._api_user
        if user.has_group("telegram_base.group_telegram_admin"):
            permission = "admin"
        elif user.has_group("telegram_base.group_telegram_dev"):
            permission = "dev"
        else:
            permission = "freela"

        response, tool_calls, usage = request.env["telegram.ai.chat"].chat(
            message, user, permission
        )
        return _json_response({
            "response": response,
            "tool_calls": tool_calls,
            "usage": usage,
        })

    @http.route("/api/v1/search", type="http", auth="none", methods=["POST"], csrf=False)
    @_authenticate
    def search(self):
        try:
            data = json.loads(request.httprequest.get_data(as_text=True))
        except (json.JSONDecodeError, TypeError):
            return _json_response({"error": "Invalid JSON body"}, 400)
        model = data.get("model")
        domain = data.get("domain", [])
        fields_list = data.get("fields")
        limit = data.get("limit", 10)
        order = data.get("order", "")

        if not model:
            return _json_response({"error": "model is required"}, 400)

        # Enforce same permission checks as AI tools
        user = request._api_user
        if user.has_group("telegram_base.group_telegram_admin"):
            permission = "admin"
        elif user.has_group("telegram_base.group_telegram_dev"):
            permission = "dev"
        else:
            permission = "freela"

        ai_chat = request.env["telegram.ai.chat"]
        result = ai_chat._tool_search_odoo(
            {"model": model, "domain": domain, "fields": fields_list,
             "limit": limit, "order": order},
            user, permission,
        )
        if "error" in result:
            return _json_response(result, 403)
        return _json_response(result)

    @http.route("/api/v1/models", type="http", auth="none", methods=["GET"], csrf=False)
    @_authenticate
    def list_models(self):
        term = request.params.get("q", "")
        domain = [("model", "ilike", term)] if term else []
        models = request.env["ir.model"].search_read(
            domain, ["model", "name"], order="model asc"
        )
        return _json_response({"models": models})

    @http.route(
        "/api/v1/models/<string:model_name>/fields",
        type="http", auth="none", methods=["GET"], csrf=False,
    )
    @_authenticate
    def model_fields(self, model_name):
        try:
            Model = request.env[model_name]
        except KeyError:
            return _json_response({"error": f"Model {model_name} not found"}, 404)

        fields_info = Model.fields_get(attributes=["string", "type", "relation", "required"])
        return _json_response({"model": model_name, "fields": fields_info})
