"""Async XML-RPC client for Odoo.

Wraps xmlrpc.client calls in asyncio.to_thread to avoid blocking the event loop.
"""

import asyncio
import logging
import xmlrpc.client
from typing import Any

logger = logging.getLogger(__name__)


class OdooClient:
    """Async wrapper around Odoo's XML-RPC API."""

    def __init__(self, url: str, db: str, user: str, password: str):
        self.url = url.rstrip("/")
        self.db = db
        self.user = user
        self.password = password
        self._uid: int | None = None
        self._common = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/common")
        self._object = xmlrpc.client.ServerProxy(f"{self.url}/xmlrpc/2/object")

    async def authenticate(self) -> int:
        """Authenticate and cache the UID."""
        self._uid = await asyncio.to_thread(
            self._common.authenticate, self.db, self.user, self.password, {}
        )
        if not self._uid:
            raise ConnectionError("Odoo authentication failed")
        logger.info("Authenticated to Odoo as uid=%s", self._uid)
        return self._uid

    @property
    def uid(self) -> int:
        if self._uid is None:
            raise RuntimeError("Call authenticate() before using the client")
        return self._uid

    async def execute(
        self, model: str, method: str, *args: Any, **kwargs: Any
    ) -> Any:
        """Execute an Odoo XML-RPC call asynchronously."""
        return await asyncio.to_thread(
            self._object.execute_kw,
            self.db,
            self.uid,
            self.password,
            model,
            method,
            list(args),
            kwargs,
        )

    async def search_read(
        self,
        model: str,
        domain: list | None = None,
        fields: list | None = None,
        limit: int = 0,
        offset: int = 0,
        order: str = "",
    ) -> list[dict]:
        """Convenience method for search_read."""
        kwargs = {}
        if fields:
            kwargs["fields"] = fields
        if limit:
            kwargs["limit"] = limit
        if offset:
            kwargs["offset"] = offset
        if order:
            kwargs["order"] = order
        return await self.execute(model, "search_read", domain or [], **kwargs)

    async def create(self, model: str, values: dict) -> int:
        """Create a record and return its ID."""
        return await self.execute(model, "create", [values])

    async def write(self, model: str, ids: list[int], values: dict) -> bool:
        """Update records."""
        return await self.execute(model, "write", ids, values)

    async def unlink(self, model: str, ids: list[int]) -> bool:
        """Delete records."""
        return await self.execute(model, "unlink", ids)

    # --- Telegram-specific helpers ---

    async def find_user_by_telegram_id(self, telegram_id: int | str) -> dict | None:
        """Find Odoo user by Telegram ID."""
        users = await self.search_read(
            "res.users",
            [("telegram_id", "=", str(telegram_id))],
            fields=["id", "name", "login", "telegram_id", "groups_id"],
            limit=1,
        )
        return users[0] if users else None

    async def find_user_by_api_token(self, token: str) -> dict | None:
        """Find Odoo user by API token."""
        if not token:
            return None
        users = await self.search_read(
            "res.users",
            [("telegram_api_token", "=", token)],
            fields=["id", "name", "login", "telegram_id", "groups_id"],
            limit=1,
        )
        return users[0] if users else None

    async def find_chat(self, chat_id: int | str) -> dict | None:
        """Find telegram.chat record by Telegram chat ID."""
        chats = await self.search_read(
            "telegram.chat",
            [("telegram_chat_id", "=", str(chat_id))],
            fields=[
                "id", "name", "telegram_chat_id", "chat_type",
                "project_id", "permission_level",
            ],
            limit=1,
        )
        return chats[0] if chats else None

    async def user_has_group(self, user_id: int, group_xmlid: str) -> bool:
        """Check if a user belongs to a specific group by XML ID."""
        group = await self.search_read(
            "ir.model.data",
            [
                ("module", "=", group_xmlid.split(".")[0]),
                ("name", "=", group_xmlid.split(".")[1]),
            ],
            fields=["res_id"],
            limit=1,
        )
        if not group:
            return False
        group_id = group[0]["res_id"]
        user = await self.search_read(
            "res.users",
            [("id", "=", user_id)],
            fields=["groups_id"],
            limit=1,
        )
        if not user:
            return False
        return group_id in user[0]["groups_id"]

    async def get_user_telegram_group(self, user_id: int) -> str | None:
        """Return the highest telegram permission group for a user."""
        for group in [
            "telegram_base.group_telegram_admin",
            "telegram_base.group_telegram_dev",
            "telegram_base.group_telegram_freela",
        ]:
            if await self.user_has_group(user_id, group):
                return group.split("_")[-1]  # admin, dev, or freela
        return None

    # --- Schema introspection helpers ---

    async def list_models(self, filter_term: str = "") -> list[dict]:
        """List available Odoo models. Optionally filter by name."""
        domain = []
        if filter_term:
            domain.append(("model", "ilike", filter_term))
        return await self.search_read(
            "ir.model",
            domain,
            fields=["model", "name", "info"],
            order="model asc",
        )

    async def get_model_fields(self, model_name: str) -> list[dict]:
        """Get field definitions for a given model."""
        return await self.search_read(
            "ir.model.fields",
            [("model", "=", model_name)],
            fields=[
                "name", "field_description", "ttype", "relation",
                "required", "readonly", "store",
            ],
            order="name asc",
        )
