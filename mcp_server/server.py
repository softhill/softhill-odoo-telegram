"""MCP Server for Odoo via Bot REST API.

This MCP server connects to the bot's REST API (not directly to Odoo),
inheriting all permission controls from the bot layer.

Usage with Claude Code:
    Add to ~/.claude/claude_desktop_config.json:
    {
        "mcpServers": {
            "odoo": {
                "command": "python",
                "args": ["-m", "mcp_server.server"],
                "env": {
                    "SOFTHILL_BOT_URL": "https://bot.softhill.com.br",
                    "SOFTHILL_BOT_TOKEN": "your-api-token"
                }
            }
        }
    }
"""

import json
import os
import sys
from typing import Any

import httpx
from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import Tool, TextContent

BOT_URL = os.environ.get("SOFTHILL_BOT_URL", "http://localhost:8080")
BOT_TOKEN = os.environ.get("SOFTHILL_BOT_TOKEN", "")

server = Server("odoo-telegram")

_client: httpx.AsyncClient | None = None


async def get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(
            base_url=BOT_URL,
            headers={"Authorization": f"Bearer {BOT_TOKEN}"},
            timeout=30.0,
        )
    return _client


async def _api_get(path: str, params: dict | None = None) -> dict:
    client = await get_client()
    resp = await client.get(path, params=params)
    resp.raise_for_status()
    return resp.json()


async def _api_post(path: str, data: dict | None = None) -> dict:
    client = await get_client()
    resp = await client.post(path, json=data or {})
    resp.raise_for_status()
    return resp.json()


def _format(data: Any) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False, default=str)


# --- Tool definitions ---

@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="list_tasks",
            description="Lista tasks do usuario. Filtra por projeto opcionalmente.",
            inputSchema={
                "type": "object",
                "properties": {
                    "project": {
                        "type": "string",
                        "description": "Nome do projeto para filtrar",
                    }
                },
            },
        ),
        Tool(
            name="create_task",
            description="Cria uma nova task no Odoo.",
            inputSchema={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Nome da task"},
                    "project_id": {"type": "integer", "description": "ID do projeto"},
                    "description": {"type": "string", "description": "Descricao"},
                },
                "required": ["name", "project_id"],
            },
        ),
        Tool(
            name="list_hours",
            description="Lista horas registradas do usuario.",
            inputSchema={
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "enum": ["today", "week", "month"],
                        "description": "Periodo para consulta",
                    }
                },
            },
        ),
        Tool(
            name="create_hours",
            description=(
                "Registra horas no Odoo. "
                "Requer permissao admin via API ou ser via Telegram para outros grupos."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "project_id": {"type": "integer", "description": "ID do projeto"},
                    "task_id": {"type": "integer", "description": "ID da task"},
                    "hours": {"type": "number", "description": "Quantidade de horas"},
                    "description": {"type": "string", "description": "Descricao do trabalho"},
                },
                "required": ["project_id", "hours", "description"],
            },
        ),
        Tool(
            name="list_projects",
            description="Lista projetos disponiveis.",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="list_changes",
            description="Lista change requests (solicitacoes de mudanca).",
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="request_deploy",
            description="Solicita deploy/promocao de ambiente. Precisa aprovacao admin.",
            inputSchema={
                "type": "object",
                "properties": {
                    "modules": {"type": "string", "description": "Modulos separados por virgula"},
                    "source_env": {"type": "string", "enum": ["dev", "hml", "prod"]},
                    "target_env": {"type": "string", "enum": ["dev", "hml", "prod"]},
                    "description": {"type": "string", "description": "Descricao da mudanca"},
                },
                "required": ["modules", "target_env", "description"],
            },
        ),
        Tool(
            name="approve_change",
            description="Aprova uma change request. Requer grupo admin.",
            inputSchema={
                "type": "object",
                "properties": {
                    "change_id": {"type": "integer", "description": "ID da change request"},
                },
                "required": ["change_id"],
            },
        ),
        Tool(
            name="ask_ai",
            description=(
                "Pergunta livre para a IA do bot (com contexto da empresa). "
                "Use para consultas sobre projetos, status, ou duvidas operacionais."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "question": {"type": "string", "description": "Sua pergunta"},
                },
                "required": ["question"],
            },
        ),
        Tool(
            name="list_models",
            description="Lista modelos Odoo disponiveis. Admin/dev apenas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "filter": {
                        "type": "string",
                        "description": "Filtro por nome do modelo (ex: 'project', 'sale')",
                    }
                },
            },
        ),
        Tool(
            name="get_model_fields",
            description="Retorna campos de um modelo Odoo. Admin/dev apenas.",
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {
                        "type": "string",
                        "description": "Nome tecnico do modelo (ex: 'project.task')",
                    }
                },
                "required": ["model"],
            },
        ),
        Tool(
            name="search_records",
            description=(
                "Busca generica em qualquer modelo Odoo. Admin/dev apenas. "
                "Use list_models e get_model_fields para descobrir o schema antes."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "model": {"type": "string", "description": "Nome do modelo"},
                    "domain": {
                        "type": "array",
                        "description": "Filtros no formato Odoo domain (ex: [['state','=','sale']])",
                    },
                    "fields": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Campos para retornar",
                    },
                    "limit": {"type": "integer", "description": "Limite de registros"},
                    "order": {"type": "string", "description": "Ordenacao (ex: 'create_date desc')"},
                },
                "required": ["model"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        result = await _dispatch(name, arguments)
        return [TextContent(type="text", text=_format(result))]
    except httpx.HTTPStatusError as e:
        error_body = e.response.text
        return [TextContent(
            type="text",
            text=f"API error {e.response.status_code}: {error_body}",
        )]


async def _dispatch(name: str, args: dict) -> Any:
    match name:
        case "list_tasks":
            params = {}
            if args.get("project"):
                params["project"] = args["project"]
            return await _api_get("/api/v1/tasks", params)

        case "create_task":
            return await _api_post("/api/v1/tasks", args)

        case "list_hours":
            params = {}
            if args.get("period"):
                params["period"] = args["period"]
            return await _api_get("/api/v1/hours", params)

        case "create_hours":
            return await _api_post("/api/v1/hours", args)

        case "list_projects":
            return await _api_get("/api/v1/projects")

        case "list_changes":
            return await _api_get("/api/v1/changes")

        case "request_deploy":
            return await _api_post("/api/v1/changes", {
                "change_type": "promote",
                "source_env": args.get("source_env"),
                "target_env": args["target_env"],
                "modules": args["modules"],
                "description": args["description"],
            })

        case "approve_change":
            change_id = args["change_id"]
            return await _api_post(f"/api/v1/changes/{change_id}/approve")

        case "ask_ai":
            return await _api_post("/api/v1/chat", {"message": args["question"]})

        case "list_models":
            params = {}
            if args.get("filter"):
                params["filter"] = args["filter"]
            return await _api_get("/api/v1/models", params)

        case "get_model_fields":
            model = args["model"]
            return await _api_get(f"/api/v1/models/{model}")

        case "search_records":
            return await _api_post("/api/v1/search", args)

        case _:
            return {"error": f"Unknown tool: {name}"}


async def main():
    async with run_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream)


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
