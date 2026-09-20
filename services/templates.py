"""Daily spawn of recurring tasks from the قالب sheet."""

from __future__ import annotations

import logging

import jdatetime
from aiogram import Bot

from services.sheets import Personnel
from services.sheets_async import SheetsAsync
from services.sheets_models import (
    TEMPLATE_CREATED_BY,
    TemplateEntry,
    jalali_to_str,
    next_run_on_or_after,
    parse_due_as_jalali,
    tehran_today,
    template_is_due,
)

logger = logging.getLogger(__name__)


def _due_for_entry(entry: TemplateEntry, today: jdatetime.date) -> str:
    from services.sheets_models import due_date_from_lead

    return due_date_from_lead(today, entry.lead_days)


def _next_after_today(entry: TemplateEntry, today: jdatetime.date) -> str:
    tomorrow = today + jdatetime.timedelta(days=1)
    start = parse_due_as_jalali(entry.start_date)
    nxt = next_run_on_or_after(
        recurrence=entry.recurrence,
        day_base=entry.day_base,
        start=start,
        on_or_after=tomorrow,
    )
    return jalali_to_str(nxt or tomorrow)


def _match_person(name: str, people: list[Personnel]) -> Personnel | None:
    needle = name.strip().lower()
    exact = [person for person in people if person.name.strip().lower() == needle]
    if len(exact) == 1:
        return exact[0]
    if exact:
        return exact[0]
    contains = [person for person in people if needle in person.name.lower()]
    if len(contains) == 1:
        return contains[0]
    return None


async def run_template_pass(bot: Bot) -> int:
    """Create due template tasks. Returns number of Task rows created."""
    today = tehran_today()
    today_str = jalali_to_str(today)
    try:
        entries = await SheetsAsync.list_template_entries()
    except Exception:
        logger.exception("قالب sheet read failed")
        return 0

    due_entries = [entry for entry in entries if template_is_due(entry, today)]
    if not due_entries:
        logger.info("No قالب rows due today.")
        return 0

    try:
        people = await SheetsAsync.get_active_personnel()
    except Exception:
        logger.exception("قالب personnel read failed")
        return 0

    created = 0
    from bot.task_notify import schedule_new_task_sms, send_new_task_pv

    for entry in due_entries:
        spawned = 0
        due_date = _due_for_entry(entry, today)
        for name in entry.assignee_names:
            person = _match_person(name, people)
            if person is None:
                logger.warning("قالب skip unknown assignee %r row=%s", name, entry.row_index)
                continue
            try:
                task = await SheetsAsync.create_task(
                    title=entry.title,
                    project=entry.project or "عمومی",
                    assignee=person,
                    created_by_name=TEMPLATE_CREATED_BY,
                    priority=entry.priority,
                    due_date=due_date,
                )
            except Exception:
                logger.exception(
                    "قالب create_task failed row=%s assignee=%s",
                    entry.row_index,
                    person.name,
                )
                continue
            spawned += 1
            created += 1
            await send_new_task_pv(bot, person, task, TEMPLATE_CREATED_BY)
            schedule_new_task_sms(person, task, TEMPLATE_CREATED_BY)

        if spawned <= 0:
            logger.warning("قالب row %s produced no tasks", entry.row_index)
            continue
        try:
            await SheetsAsync.update_template_run(
                entry.row_index,
                last_run=today_str,
                next_run=_next_after_today(entry, today),
            )
        except Exception:
            logger.exception("قالب run dates update failed row=%s", entry.row_index)

    logger.info("قالب pass done: due=%s created=%s", len(due_entries), created)
    return created
