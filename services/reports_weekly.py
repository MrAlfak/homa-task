"""Friday summary chart for managers with گزارش هفتگی enabled."""

from __future__ import annotations

import logging

import jdatetime
from aiogram import Bot
from aiogram.types import BufferedInputFile

from services.auth import enabled_report_kinds
from services.overdue import _load_notified, _save_notified
from services.sheets_async import SheetsAsync

logger = logging.getLogger(__name__)


async def run_weekly_report_pass(bot: Bot) -> None:
    today = jdatetime.date.today()
    if today.weekday() != 6:
        return
    today_str = f"{today.year:04d}/{today.month:02d}/{today.day:02d}"
    notified = _load_notified()
    if notified.get("__weekly_report__") == today_str:
        return
    people = await SheetsAsync.get_active_personnel()
    recipients = [person for person in people if person.reports_access and person.report_weekly]
    if not recipients:
        notified["__weekly_report__"] = today_str
        _save_notified(notified)
        return
    tasks = await SheetsAsync.list_main_tasks()
    from services.charts import render_report

    sent = 0
    for person in recipients:
        kinds = enabled_report_kinds(person)
        try:
            png = render_report("summary", tasks, kinds=kinds)
            await bot.send_photo(
                person.telegram_id,
                BufferedInputFile(png, filename="weekly-report.png"),
                caption="📊 خلاصه هفتگی تسک‌ها",
            )
            sent += 1
        except Exception:
            logger.warning("Weekly report failed for %s", person.name, exc_info=True)
    notified["__weekly_report__"] = today_str
    _save_notified(notified)
    logger.info("Weekly reports sent=%s recipients=%s", sent, len(recipients))
