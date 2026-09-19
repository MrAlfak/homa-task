"""Private Telegram + SMS notify after a task is created."""

from __future__ import annotations

import logging

from aiogram import Bot

from bot.formatting import esc
from services.sheets import Personnel, Task

logger = logging.getLogger(__name__)


def format_new_task_pv(task: Task, *, creator_name: str) -> str:
    return (
        f"📌 <b>تسک جدید</b>\n\n"
        f"📋 {esc(task.title)}\n"
        f"📁 {esc(task.project)}\n"
        f"⚡ {esc(task.priority)}\n"
        f"👤 از طرف: {esc(creator_name)}\n"
        f"📅 ددلاین: {esc(task.due_date)}"
    )


async def send_new_task_pv(bot: Bot, person: Personnel, task: Task, creator_name: str) -> bool:
    """Send the task to the assignee's Telegram PV. True if sent or skipped."""
    if not person.telegram_notify or person.telegram_id <= 0:
        logger.info("Telegram PV skipped for %s (ارسال تلگرام=FALSE)", person.name)
        return True
    try:
        await bot.send_message(
            chat_id=person.telegram_id,
            text=format_new_task_pv(task, creator_name=creator_name),
            parse_mode="HTML",
        )
        return True
    except Exception:
        logger.warning(
            "assignee Telegram notify failed for %s",
            person.telegram_id,
            exc_info=True,
        )
        return False


def schedule_new_task_sms(person: Personnel, task: Task, creator_name: str) -> None:
    try:
        from services.sms import notify_new_task, schedule

        schedule(notify_new_task(person, task, creator_name))
    except Exception:
        logger.warning("SMS new-task schedule failed", exc_info=True)
