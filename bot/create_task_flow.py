"""Shared helpers for the admin create-task FSM flow."""

from __future__ import annotations

import logging
from collections.abc import Awaitable
from typing import TypeVar

from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message

logger = logging.getLogger(__name__)

T = TypeVar("T")

SHEETS_ERROR_TEXT = (
    "⚠️ اتصال به Google Sheet برقرار نشد یا کند است.\n"
    "چند ثانیه صبر کنید و دوباره «➕ ثبت تسک جدید» را بزنید."
)

FLOW_EXPIRED_TEXT = (
    "⏱️ فرایند ثبت تسک منقضی شده (مثلاً بعد از ری‌استارت ربات).\n"
    "لطفاً دوباره «➕ ثبت تسک جدید» را از منو بزنید."
)

INCOMPLETE_DATA_TEXT = (
    "اطلاعات ثبت تسک ناقص است.\n"
    "لطفاً دوباره «➕ ثبت تسک جدید» را از منو بزنید."
)

ASSIGNEE_NOTIFY_FAILED_TEXT = (
    "⚠️ تسک در Google Sheet ثبت شد، ولی اعلان به <b>{name}</b> ارسال نشد.\n"
    "احتمالاً آن کارمند هنوز ربات را استارت نکرده — از او بخواهید یک‌بار "
    "<b>/start</b> بزند (این مربوط به شما نیست)."
)


async def run_sheets_step(
    message: Message,
    label: str,
    coro: Awaitable[T],
) -> T | None:
    """Run a Sheets call; on failure log and reply without involving /start recovery."""
    try:
        return await coro
    except Exception:
        logger.exception("Sheets step failed during create-task (%s)", label)
        await message.answer(SHEETS_ERROR_TEXT)
        return None


async def safe_edit_text(message: Message, text: str, **kwargs) -> bool:
    """Edit a callback message; fall back to answer() if edit is not possible."""
    try:
        await message.edit_text(text, **kwargs)
        return True
    except TelegramBadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return True
        logger.warning("edit_text failed, sending new message: %s", exc)
    except Exception:
        logger.exception("edit_text failed, sending new message")
    try:
        await message.answer(text, **kwargs)
    except Exception:
        logger.exception("answer fallback after edit_text failed")
        return False
    return True


async def safe_answer(message: Message, text: str, **kwargs) -> bool:
    """Send a message; never raise to the global error middleware."""
    try:
        await message.answer(text, **kwargs)
        return True
    except Exception:
        logger.exception("safe_answer failed")
        return False
