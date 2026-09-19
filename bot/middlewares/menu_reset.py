"""Leave FSM text steps when the user taps a main-menu reply button.

Title / location / idea handlers match any ``F.text``. Without clearing
state *before* handler lookup, «تسک‌های من» during create-task is stored
as the title instead of opening the task list.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, TelegramObject

from bot.keyboards import is_menu_text

logger = logging.getLogger(__name__)


class MenuResetMiddleware(BaseMiddleware):
    """Clear FSM on main-menu taps so the matching menu handler can run."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        if isinstance(event, Message) and event.text:
            text = event.text.strip()
            if is_menu_text(text):
                state: FSMContext | None = data.get("state")
                if state is not None:
                    current = await state.get_state()
                    if current is not None:
                        logger.info("Menu tap %r left FSM state %s", text[:40], current)
                        await state.clear()
        return await handler(event, data)
