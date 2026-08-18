"""Instant user feedback before slow handlers run."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.enums import ChatAction
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class InstantFeedbackMiddleware(BaseMiddleware):
    """Show typing indicator immediately so users know the tap was received."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        if isinstance(event, Message) and bot is not None and event.chat is not None:
            asyncio.create_task(
                _safe_chat_action(bot, event.chat.id, ChatAction.TYPING),
                name="instant-typing",
            )
        return await handler(event, data)


async def _safe_chat_action(bot, chat_id: int, action: ChatAction) -> None:
    try:
        await bot.send_chat_action(chat_id, action)
    except Exception:
        logger.debug("send_chat_action failed", exc_info=True)
