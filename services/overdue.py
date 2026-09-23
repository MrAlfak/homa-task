"""Periodic overdue-task reminders and Google Sheet row highlighting."""

from __future__ import annotations

import asyncio
import datetime
import json
import logging
from collections import defaultdict
from pathlib import Path

import jdatetime
from aiogram import Bot

from bot.formatting import esc
from config import config
from services.sheets import Personnel, Task
from services.sheets_async import SheetsAsync
from services.sheets_models import (
    TEHRAN_TZ,
    normalize_name,
    tehran_now,
    tehran_today,
    today_jalali_str,
)

logger = logging.getLogger(__name__)

# How often to re-scan Sheets / re-color / remind (seconds).
OVERDUE_INTERVAL_SEC = 3600.0
# Delay after bot startup before the first pass (Sheets warm-up).
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


async def _notify_group(bot: Bot, overdue: list[Task], notified: dict[str, str], today_str: str) -> None:
    if not config.group_chat_id or notified.get("__group__") == today_str:
        return
    try:
        await bot.send_message(
            config.group_chat_id,
            _format_assignee_digest(overdue),
            parse_mode="HTML",
        )
        notified["__group__"] = today_str
    except Exception:
        logger.warning("Overdue group notify failed", exc_info=True)


async def _personnel_by_name() -> dict[str, Personnel]:
    people = await SheetsAsync.get_all_active_personnel()
    mapping: dict[str, Personnel] = {}
    for p in people:
        mapping[p.name.strip()] = p
        mapping[normalize_name(p.name).lower()] = p
    return mapping


async def run_overdue_pass(bot: Bot) -> None:
    """Color overdue rows in Sheets and DM assignees (once per Jalali day per task)."""
    today_str = today_jalali_str()

    try:
        color_stats, overdue = await SheetsAsync.sync_overdue_row_colors()
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
        await _notify_group(bot, overdue, notified, today_str)
        _save_notified(notified)
        return

    name_map = await _personnel_by_name()
    sent = 0
    for name, tasks in by_assignee.items():
        clean_name = normalize_name(name).lower()
        person = name_map.get(name.strip()) or name_map.get(clean_name)
        if person is None:
            logger.warning("Overdue notify skipped — unknown assignee %r", name)
            continue

        if person.telegram_id > 0:
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

        sms_key = f"sms|{name}"
        if notified.get(sms_key) != today_str and person.sms_enabled:
            try:
                from services.sms import notify_overdue

                await notify_overdue(person, tasks)
            except Exception:
                logger.warning("Overdue SMS failed for %s", name, exc_info=True)
            notified[sms_key] = today_str

    await _notify_group(bot, overdue, notified, today_str)
    _save_notified(notified)
    logger.info(
        "Overdue notify done: open=%d digests_sent=%d",
        len(overdue),
        sent,
    )


async def send_daily_morning_digest(bot: Bot) -> None:
    """Send daily morning briefing (08:00–10:00 Tehran time) with open task summary to active personnel."""
    now_tehran = tehran_now()
    if not (8 <= now_tehran.hour < 10):
        return

    today_str = today_jalali_str()

    notified = _load_notified()
    personnel_list = await SheetsAsync.get_active_personnel()

    sent_count = 0
    for person in personnel_list:
        if not person.telegram_id or person.telegram_id <= 0:
            continue
        notify_key = f"morning_digest|{person.telegram_id}"
        if notified.get(notify_key) == today_str:
            continue

        try:
            tasks = await SheetsAsync.get_tasks_for_assignee(person)
            open_tasks = [t for t in tasks if t.status in ("pending", "in_progress")]
            if not open_tasks:
                notified[notify_key] = today_str
                continue

            urgent_count = sum(1 for t in open_tasks if (t.priority or "").lower() == "high")
            due_today_count = sum(1 for t in open_tasks if t.due_date and t.due_date.strip() == today_str)

            urgent_line = f"\n⚡ <b>{urgent_count} تسک فوری</b>" if urgent_count > 0 else ""
            due_today_line = f"\n📅 <b>{due_today_count} تسک با ددلاین امروز</b>" if due_today_count > 0 else ""

            msg = (
                f"🌅 <b>سلام {esc(person.name)} عزیز، صبح بخیر!</b>\n\n"
                f"📋 <b>خلاصه وضعیت تسک‌های امروز شما:</b>\n"
                f"⏳ در مجموع <b>{len(open_tasks)} تسک</b> در انتظار انجام دارید.{urgent_line}{due_today_line}\n\n"
                "برای مشاهده جزئیات می‌توانید از دکمه «📌 تسک‌های من» در منوی ربات استفاده کنید.\n"
                "روز پرانرژی و پربرکتی داشته باشید! ✨"
            )
            await bot.send_message(person.telegram_id, msg, parse_mode="HTML")
            notified[notify_key] = today_str
            sent_count += 1
        except Exception:
            logger.warning("Morning digest failed for %s (%s)", person.name, person.telegram_id, exc_info=True)

    if sent_count > 0:
        _save_notified(notified)
        logger.info("Morning digest sent to %d personnel.", sent_count)


async def overdue_supervisor(bot: Bot) -> None:
    """Background loop: sync colors + remind assignees about overdue tasks."""
    # Allow full startup warmup quota to replenish before running background synchronization
    await asyncio.sleep(max(60.0, OVERDUE_STARTUP_DELAY_SEC))
    while True:
        try:
            status_stats = await SheetsAsync.sync_tasks_status_from_personal()
            logger.info("Tasks status synced from personal tabs: %s", status_stats)
        except Exception:
            logger.exception("Tasks status sync from personal tabs failed")
        try:
            await run_overdue_pass(bot)
        except Exception:
            logger.exception("Overdue supervisor pass crashed")
        try:
            await send_daily_morning_digest(bot)
        except Exception:
            logger.exception("Morning digest pass crashed")
        try:
            from services.templates import run_template_pass

            await run_template_pass(bot)
        except Exception:
            logger.exception("Template supervisor pass crashed")
        try:
            from services.reports_weekly import run_weekly_report_pass

            await run_weekly_report_pass(bot)
        except Exception:
            logger.exception("Weekly report pass crashed")
        await asyncio.sleep(OVERDUE_INTERVAL_SEC)
