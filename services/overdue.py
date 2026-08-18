"""Periodic overdue-task reminders and Google Sheet row highlighting."""

from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict
from pathlib import Path

import jdatetime
from aiogram import Bot

from bot.formatting import esc
from services.sheets import Personnel, Task
from services.sheets_async import SheetsAsync

logger = logging.getLogger(__name__)

# How often to re-scan Sheets / re-color / remind (seconds).
OVERDUE_INTERVAL_SEC = 3600.0
# Delay after bot startup before the first pass (Sheets + proxy warm-up).
OVERDUE_STARTUP_DELAY_SEC = 45.0

_NOTIFIED_PATH = Path("/tmp/homa_overdue_notified.json")


def _load_notified() -> dict[str, str]:
    """Map notify-key → Jalali day string when last notified."""
    try:
        raw = _NOTIFIED_PATH.read_text(encoding="utf-8")
        data = json.loads(raw)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
    except Exception:
        pass
    return {}


def _save_notified(data: dict[str, str]) -> None:
    try:
        _NOTIFIED_PATH.write_text(
            json.dumps(data, ensure_ascii=False, indent=0),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.warning("Could not persist overdue notify state: %s", exc)


def _notify_key(task: Task) -> str:
    due = task.due_date.strip().lstrip("'")
    return f"{task.assignee_name}|{task.title}|{due}"


def _format_assignee_digest(tasks: list[Task]) -> str:
    lines = [
        "⚠️ <b>تسک‌های عقب‌افتاده</b>",
        "",
        "ددلاین این تسک‌ها گذشته و هنوز انجام نشده‌اند:",
        "",
    ]
    for task in tasks[:20]:
        lines.append(
            f"• <b>{esc(task.title)}</b>\n"
            f"  📁 {esc(task.project)} · 📅 {esc(task.due_date)} · ⚡ {esc(task.priority)}"
        )
    if len(tasks) > 20:
        lines.append(f"\n… و {len(tasks) - 20} مورد دیگر")
    lines.append("\nلطفاً وضعیت را در ربات به‌روز کنید یا تسک را انجام دهید.")
    return "\n".join(lines)


async def _personnel_by_name() -> dict[str, Personnel]:
    people = await SheetsAsync.get_active_personnel()
    return {p.name: p for p in people}


async def run_overdue_pass(bot: Bot) -> None:
    """Color overdue rows in Sheets and DM assignees (once per Jalali day per task)."""
    today = jdatetime.date.today()
    today_str = f"{today.year:04d}/{today.month:02d}/{today.day:02d}"

    try:
        color_stats = await SheetsAsync.sync_overdue_row_colors()
        logger.info(
            "Overdue sheet colors synced: painted=%s cleared=%s requests=%s",
            color_stats.get("painted"),
            color_stats.get("cleared"),
            color_stats.get("requests"),
        )
    except Exception:
        logger.exception("Overdue sheet coloring failed")

    try:
        overdue = await SheetsAsync.list_overdue_open_tasks()
    except Exception:
        logger.exception("Overdue task listing failed")
        return

    if not overdue:
        logger.info("No open overdue tasks.")
        return

    notified = _load_notified()
    # Keep only today's keys so the file does not grow forever.
    notified = {k: v for k, v in notified.items() if v == today_str}

    by_assignee: dict[str, list[Task]] = defaultdict(list)
    for task in overdue:
        key = _notify_key(task)
        if notified.get(key) == today_str:
            continue
        by_assignee[task.assignee_name].append(task)

    if not by_assignee:
        logger.info("Overdue tasks already notified today (%d open).", len(overdue))
        _save_notified(notified)
        return

    name_map = await _personnel_by_name()
    sent = 0
    for name, tasks in by_assignee.items():
        person = name_map.get(name)
        if person is None or person.telegram_id <= 0:
            logger.warning("Overdue notify skipped — no telegram id for %r", name)
            continue
        try:
            await bot.send_message(
                person.telegram_id,
                _format_assignee_digest(tasks),
                parse_mode="HTML",
            )
            sent += 1
            for task in tasks:
                notified[_notify_key(task)] = today_str
        except Exception:
            logger.warning(
                "Overdue notify failed for %s (%s)",
                name,
                person.telegram_id,
                exc_info=True,
            )

    _save_notified(notified)
    logger.info(
        "Overdue notify done: open=%d digests_sent=%d",
        len(overdue),
        sent,
    )


async def overdue_supervisor(bot: Bot) -> None:
    """Background loop: sync colors + remind assignees about overdue tasks."""
    await asyncio.sleep(OVERDUE_STARTUP_DELAY_SEC)
    while True:
        try:
            await run_overdue_pass(bot)
        except Exception:
            logger.exception("Overdue supervisor pass crashed")
        await asyncio.sleep(OVERDUE_INTERVAL_SEC)
