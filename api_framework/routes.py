"""Generic REST API routes for Odoo-Telegram integration.

These routes proxy requests to Odoo via the OdooClient, respecting
user permissions and channel guards (HUMAN_ONLY_ACTIONS).
"""

import logging

from aiohttp import web

from bot_framework.channel_guard import ChannelGuard
from bot_framework.odoo_client import OdooClient
from bot_framework.telegram_auth import UserContext

logger = logging.getLogger(__name__)


def setup_api_routes(app: web.Application) -> None:
    """Register all API routes on the aiohttp application."""
    app.router.add_get("/health", health)
    app.router.add_get("/api/v1/tasks", get_tasks)
    app.router.add_post("/api/v1/tasks", create_task)
    app.router.add_get("/api/v1/hours", get_hours)
    app.router.add_post("/api/v1/hours", create_hours)
    app.router.add_get("/api/v1/projects", get_projects)
    app.router.add_get("/api/v1/changes", get_changes)
    app.router.add_post("/api/v1/changes", create_change)
    app.router.add_post("/api/v1/changes/{change_id}/approve", approve_change)
    app.router.add_post("/api/v1/chat", chat)


async def health(request: web.Request) -> web.Response:
    return web.json_response({"status": "ok"})


def _get_ctx(request: web.Request) -> tuple[UserContext, OdooClient]:
    return request["user_ctx"], request.app["odoo"]


# --- Tasks ---

async def get_tasks(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)
    project = request.query.get("project")

    domain = []
    if ctx.effective_permission == "freela":
        domain.append(("user_ids", "in", [ctx.odoo_user_id]))
    elif ctx.project_id:
        domain.append(("project_id", "=", ctx.project_id))
    if project:
        domain.append(("project_id.name", "ilike", project))

    tasks = await odoo.search_read(
        "project.task",
        domain,
        fields=["id", "name", "stage_id", "user_ids", "project_id", "date_deadline"],
        order="date_deadline asc",
    )
    return web.json_response({"tasks": tasks})


async def create_task(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)
    data = await request.json()

    values = {
        "name": data.get("name", ""),
        "project_id": data.get("project_id"),
        "description": data.get("description", ""),
    }
    if data.get("user_ids"):
        values["user_ids"] = [(6, 0, data["user_ids"])]

    task_id = await odoo.create("project.task", values)
    return web.json_response({"task_id": task_id}, status=201)


# --- Hours ---

async def get_hours(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)

    domain = [("user_id", "=", ctx.odoo_user_id)]
    period = request.query.get("period", "week")
    if period == "today":
        from datetime import date
        domain.append(("date", "=", date.today().isoformat()))

    hours = await odoo.search_read(
        "account.analytic.line",
        domain,
        fields=["id", "name", "date", "unit_amount", "project_id", "task_id"],
        order="date desc",
        limit=50,
    )
    return web.json_response({"hours": hours})


async def create_hours(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)
    ChannelGuard.require("create_hours", ctx.channel)

    data = await request.json()
    values = {
        "name": data.get("description", "/"),
        "project_id": data.get("project_id"),
        "task_id": data.get("task_id"),
        "unit_amount": data.get("hours", 0),
        "user_id": ctx.odoo_user_id,
    }
    line_id = await odoo.create("account.analytic.line", values)
    return web.json_response({"line_id": line_id}, status=201)


# --- Projects ---

async def get_projects(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)

    domain = []
    if ctx.effective_permission == "freela":
        domain.append(("task_ids.user_ids", "in", [ctx.odoo_user_id]))

    projects = await odoo.search_read(
        "project.project",
        domain,
        fields=["id", "name", "partner_id", "task_count"],
    )
    return web.json_response({"projects": projects})


# --- Changes ---

async def get_changes(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)

    domain = [("is_change_request", "=", True)]
    if ctx.effective_permission != "admin":
        domain.append(("user_ids", "in", [ctx.odoo_user_id]))

    changes = await odoo.search_read(
        "project.task",
        domain,
        fields=[
            "id", "name", "stage_id", "change_type",
            "source_env", "target_env", "modules",
        ],
        order="create_date desc",
    )
    return web.json_response({"changes": changes})


async def create_change(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)
    data = await request.json()

    # Find the Change Management project
    projects = await odoo.search_read(
        "project.project",
        [("name", "ilike", "Change Management")],
        fields=["id"],
        limit=1,
    )
    if not projects:
        return web.json_response(
            {"error": "Change Management project not found"},
            status=404,
        )

    values = {
        "name": data.get("description", "Change Request"),
        "project_id": projects[0]["id"],
        "is_change_request": True,
        "change_type": data.get("change_type", "deploy"),
        "source_env": data.get("source_env"),
        "target_env": data.get("target_env"),
        "modules": data.get("modules", ""),
        "user_ids": [(6, 0, [ctx.odoo_user_id])],
    }
    task_id = await odoo.create("project.task", values)
    return web.json_response({"change_id": task_id}, status=201)


async def approve_change(request: web.Request) -> web.Response:
    ctx, odoo = _get_ctx(request)
    ChannelGuard.require("approve_change", ctx.channel)

    if ctx.effective_permission != "admin":
        return web.json_response(
            {"error": "Only admins can approve changes"},
            status=403,
        )

    change_id = int(request.match_info["change_id"])

    # Find "Aprovado" stage
    stages = await odoo.search_read(
        "project.task.type",
        [("name", "ilike", "Aprovado")],
        fields=["id"],
        limit=1,
    )
    if stages:
        await odoo.write("project.task", [change_id], {"stage_id": stages[0]["id"]})

    return web.json_response({"status": "approved", "change_id": change_id})


# --- Chat (placeholder - implemented in private repo) ---

async def chat(request: web.Request) -> web.Response:
    """AI chat endpoint. Override this in your private implementation."""
    return web.json_response(
        {"error": "Chat endpoint not configured. Override in your implementation."},
        status=501,
    )
