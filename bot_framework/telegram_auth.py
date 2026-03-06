"""Authentication middleware for aiogram 3.

Resolves Telegram user → Odoo user → permission group.
Attaches user context to each incoming message/callback.
"""

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import Message, CallbackQuery, TelegramObject

from .odoo_client import OdooClient

logger = logging.getLogger(__name__)


class UserContext:
    """Resolved user context attached to each request."""

    __slots__ = (
        "odoo_user_id", "odoo_user_name", "telegram_group",
        "chat_permission", "chat_type", "project_id", "channel",
    )

    def __init__(
        self,
        odoo_user_id: int,
        odoo_user_name: str,
        telegram_group: str,
        chat_permission: str,
        chat_type: str,
        project_id: int | None = None,
        channel: str = "telegram",
    ):
        self.odoo_user_id = odoo_user_id
        self.odoo_user_name = odoo_user_name
        self.telegram_group = telegram_group
        self.chat_permission = chat_permission
        self.chat_type = chat_type
        self.project_id = project_id
        self.channel = channel

    @property
    def effective_permission(self) -> str:
        """The effective permission is the most restrictive between user and chat."""
        levels = {"freela": 0, "dev": 1, "admin": 2}
        user_level = levels.get(self.telegram_group, -1)
        chat_level = levels.get(self.chat_permission, -1)
        effective = min(user_level, chat_level)
        for name, level in levels.items():
            if level == effective:
                return name
        return "freela"


class TelegramAuthMiddleware(BaseMiddleware):
    """Middleware that resolves Telegram user to Odoo user context."""

    def __init__(self, odoo: OdooClient):
        self.odoo = odoo

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        # Extract user and chat from the event
        user = None
        chat = None
        if isinstance(event, Message):
            user = event.from_user
            chat = event.chat
        elif isinstance(event, CallbackQuery):
            user = event.from_user
            chat = event.message.chat if event.message else None

        if not user:
            return await handler(event, data)

        # Resolve Odoo user
        odoo_user = await self.odoo.find_user_by_telegram_id(user.id)
        if not odoo_user:
            if isinstance(event, Message):
                await event.answer(
                    "Voce nao esta vinculado ao Odoo. "
                    "Use /vincular <seu_email> para se conectar."
                )
            return  # Block unlinked users

        # Resolve user group
        telegram_group = await self.odoo.get_user_telegram_group(
            odoo_user["id"]
        )
        if not telegram_group:
            if isinstance(event, Message):
                await event.answer(
                    "Sua conta Odoo nao tem permissao Telegram configurada. "
                    "Contate um administrador."
                )
            return

        # Resolve chat context
        chat_permission = telegram_group  # Default: user's own level
        chat_type = "dm"
        project_id = None

        if chat and chat.type != "private":
            chat_record = await self.odoo.find_chat(chat.id)
            if chat_record:
                chat_permission = chat_record["permission_level"]
                chat_type = chat_record["chat_type"]
                if chat_record["project_id"]:
                    project_id = chat_record["project_id"][0]
            else:
                # Unregistered group chat — deny
                if isinstance(event, Message):
                    await event.answer(
                        "Este grupo nao esta registrado no Odoo. "
                        "Um admin precisa registra-lo primeiro."
                    )
                return

        # Attach context
        data["user_ctx"] = UserContext(
            odoo_user_id=odoo_user["id"],
            odoo_user_name=odoo_user["name"],
            telegram_group=telegram_group,
            chat_permission=chat_permission,
            chat_type=chat_type,
            project_id=project_id,
            channel="telegram",
        )

        return await handler(event, data)
