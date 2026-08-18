"""User-facing error notifications when handlers fail."""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)


class UserErrorMiddleware(BaseMiddleware):
    """Log handler failures and send a friendly message instead of silence."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        try:
            return await handler(event, data)
        except Exception:
            logger.exception("Handler failed for %s", type(event).__name__)
            if isinstance(event, Message):
                await event.answer(
                    "⚠️ خطایی رخ داد. لطفاً چند ثانیه بعد دوباره تلاش کنید "
                    "یا از منو «➕ ثبت تسک جدید» را بزنید.",
                )
            elif isinstance(event, CallbackQuery):
                try:
                    await event.answer("خطا رخ داد. دوباره تلاش کنید.", show_alert=True)
                except Exception:
                    pass
            return None
