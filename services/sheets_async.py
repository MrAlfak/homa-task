"""Non-blocking wrappers for sync Google Sheets and auth I/O."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import TypeVar

import requests
from gspread.exceptions import APIError

from services.auth import AuthResult, authorize_user
from services.sheets import ContentEntry, FilmingEntry, Idea, Personnel, Task, get_sheets_service

logger = logging.getLogger(__name__)

T = TypeVar("T")

# Google Sheets API errors that are worth a quick, silent retry instead of
# immediately surfacing "خطایی رخ داد" to the user: rate limiting (429) and
# transient server-side hiccups (5xx). Anything else (permission, not-found,
# bad request) is a real error and should fail fast.
_TRANSIENT_API_CODES = {429, 500, 502, 503, 504}
_RETRY_ATTEMPTS = 3
_RETRY_BASE_DELAY = 0.6


def _is_transient_api_error(exc: APIError) -> bool:
    try:
        return exc.response.status_code in _TRANSIENT_API_CODES
    except Exception:
        return False


async def run_blocking(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run blocking work off the asyncio event loop, retrying transient failures.

    Google Sheets briefly rate-limits (HTTP 429) or hiccups (5xx) under normal
    use — especially right after a burst of taps. Without a retry, any single
    blip bubbles all the way up as a generic error message that forces the
    user to press /start again. A couple of short, silent retries make the
    bot recover on its own in the common case.
    """
    last_exc: Exception | None = None
    for attempt in range(_RETRY_ATTEMPTS):
        try:
            return await asyncio.to_thread(func, *args, **kwargs)
        except APIError as exc:
            last_exc = exc
            if not _is_transient_api_error(exc) or attempt == _RETRY_ATTEMPTS - 1:
                raise
        except (requests.exceptions.RequestException, TimeoutError, ConnectionError) as exc:
            last_exc = exc
            if attempt == _RETRY_ATTEMPTS - 1:
                raise
        delay = _RETRY_BASE_DELAY * (attempt + 1)
        logger.warning(
            "Sheets call %s failed (attempt %d/%d): %s — retrying in %.1fs",
            getattr(func, "__name__", func),
            attempt + 1,
            _RETRY_ATTEMPTS,
            last_exc,
            delay,
        )
        await asyncio.sleep(delay)
    raise last_exc  # pragma: no cover - unreachable, loop always returns/raises


async def run_once(func: Callable[..., T], /, *args, **kwargs) -> T:
    """Run blocking work off the event loop WITHOUT retrying.

    Use this for non-idempotent writes (inserting a task/idea row). Unlike
    reads, a write's HTTP response can be lost *after* Google Sheets already
    applied it (e.g. ``RemoteDisconnected``) — retrying in that case would
    silently create a duplicate row. Let the caller decide whether to ask the
    user to retry instead of guessing.
    """
    return await asyncio.to_thread(func, *args, **kwargs)


async def authorize(telegram_id: int) -> AuthResult:
    return await run_blocking(authorize_user, telegram_id)


async def warmup_caches() -> None:
    """Pre-load Personnel/Projects cache so first /start or menu tap is fast."""
    svc = get_sheets_service()
    await run_blocking(svc.ensure_projects_schema)
    await run_blocking(svc.get_active_personnel)
    await run_blocking(svc.get_projects)


class SheetsAsync:
    """Async facade over SheetsService (all methods delegate via to_thread)."""

    @staticmethod
    def _svc():
        return get_sheets_service()

    @classmethod
    async def get_active_employees(cls) -> list[Personnel]:
        return await run_blocking(cls._svc().get_active_employees)

    @classmethod
    async def get_active_personnel(cls, role: str | None = None) -> list[Personnel]:
        return await run_blocking(cls._svc().get_active_personnel, role)

    @classmethod
    async def get_personnel_by_telegram_id(
        cls, telegram_id: int, role: str | None = None
    ) -> Personnel | None:
        return await run_blocking(cls._svc().get_personnel_by_telegram_id, telegram_id, role)

    @classmethod
    async def get_projects(cls) -> list[str]:
        return await run_blocking(cls._svc().get_projects)

    @classmethod
    async def get_broadcast_recipients(cls) -> list[Personnel]:
        return await run_blocking(cls._svc().get_broadcast_recipients)

    @classmethod
    async def get_tasks_for_assignee(
        cls, personnel: Personnel, status: str | None = None
    ) -> list[Task]:
        return await run_blocking(cls._svc().get_tasks_for_assignee, personnel, status)

    @classmethod
    async def get_task_by_id(cls, task_id: str, personnel: Personnel) -> Task | None:
        return await run_blocking(cls._svc().get_task_by_id, task_id, personnel)

    @classmethod
    async def update_task_status(cls, task_id: str, personnel: Personnel, status: str) -> bool:
        return await run_blocking(cls._svc().update_task_status, task_id, personnel, status)

    @classmethod
    async def create_task(
        cls,
        *,
        title: str,
        project: str,
        assignee: Personnel,
        created_by_name: str,
        priority: str,
        due_date: str = "",
    ) -> Task:
        # Not retried: a lost response after a successful insert would
        # otherwise create a duplicate task row (see run_once docstring).
        return await run_once(
            cls._svc().create_task,
            title=title,
            project=project,
            assignee=assignee,
            created_by_name=created_by_name,
            priority=priority,
            due_date=due_date,
        )

    @classmethod
    async def create_idea(cls, personnel: Personnel, text: str) -> Idea:
        # Not retried — see create_task's comment (avoids duplicate idea rows).
        return await run_once(cls._svc().create_idea, personnel, text)

    @classmethod
    async def get_recent_ideas(cls, limit: int = 15) -> list[Idea]:
        return await run_blocking(cls._svc().get_recent_ideas, limit)

    @classmethod
    async def get_ideas_sheet_url(cls) -> str:
        return await run_blocking(cls._svc().get_ideas_sheet_url)

    @classmethod
    async def get_sheet_url(cls, personnel: Personnel) -> str:
        return await run_blocking(cls._svc().get_sheet_url, personnel)

    @classmethod
    async def list_overdue_open_tasks(cls) -> list[Task]:
        return await run_blocking(cls._svc().list_overdue_open_tasks)

    @classmethod
    async def sync_overdue_row_colors(cls) -> dict[str, int]:
        return await run_blocking(cls._svc().sync_overdue_row_colors)

    @classmethod
    async def create_filming_entry(
        cls,
        *,
        project: str,
        location: str,
        day: str,
        hour: str,
        date: str,
        assignee: Personnel,
        created_by_name: str,
    ) -> FilmingEntry:
        return await run_once(
            cls._svc().create_filming_entry,
            project=project,
            location=location,
            day=day,
            hour=hour,
            date=date,
            assignee=assignee,
            created_by_name=created_by_name,
        )

    @classmethod
    async def list_filming_entries(cls, status: str | None = None) -> list[FilmingEntry]:
        return await run_blocking(cls._svc().list_filming_entries, status)

    @classmethod
    async def get_filming_entry_by_id(cls, entry_id: str) -> FilmingEntry | None:
        return await run_blocking(cls._svc().get_filming_entry_by_id, entry_id)

    @classmethod
    async def update_filming_status(
        cls, entry_id: str, personnel: Personnel, status: str
    ) -> bool:
        return await run_blocking(cls._svc().update_filming_status, entry_id, personnel, status)

    @classmethod
    async def get_filming_sheet_url(cls) -> str:
        return await run_blocking(cls._svc().get_filming_sheet_url)

    @classmethod
    async def create_content_entry(
        cls,
        *,
        name: str,
        project: str,
        include_post: bool,
        include_story: bool,
        created_by_name: str,
    ) -> ContentEntry:
        return await run_once(
            cls._svc().create_content_entry,
            name=name,
            project=project,
            include_post=include_post,
            include_story=include_story,
            created_by_name=created_by_name,
        )

    @classmethod
    async def get_design_names(cls) -> list[str]:
        return await run_blocking(cls._svc().get_design_names)

    @classmethod
    async def list_content_entries(cls, status: str | None = None) -> list[ContentEntry]:
        return await run_blocking(cls._svc().list_content_entries, status)

    @classmethod
    async def get_content_entry_by_id(cls, entry_id: str) -> ContentEntry | None:
        return await run_blocking(cls._svc().get_content_entry_by_id, entry_id)

    @classmethod
    async def update_content_status(
        cls, entry_id: str, personnel: Personnel, status: str
    ) -> bool:
        return await run_blocking(cls._svc().update_content_status, entry_id, personnel, status)

    @classmethod
    async def get_content_sheet_url(cls) -> str:
        return await run_blocking(cls._svc().get_content_sheet_url)

    @classmethod
    async def find_personnel_by_name_hint(cls, name_hint: str) -> Personnel | None:
        return await run_blocking(cls._svc().find_personnel_by_name_hint, name_hint)

    @classmethod
    async def resolve_shamsi_date_offset(cls, day_offset: int) -> str | None:
        return await run_blocking(cls._svc().resolve_shamsi_date_offset, day_offset)

    @classmethod
    async def validate_shamsi_date(cls, value: str) -> str | None:
        return await run_blocking(cls._svc().validate_shamsi_date, value)
