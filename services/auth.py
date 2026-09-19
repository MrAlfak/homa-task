"""Personnel authorization helpers."""

from __future__ import annotations

from dataclasses import dataclass

from services.sheets_models import ContentEntry, FilmingEntry, Personnel


@dataclass(frozen=True)
class AuthResult:
    """Result of an authorization check."""

    allowed: bool
    personnel: Personnel | None = None
    reason: str = ""


def authorize_user(telegram_id: int) -> AuthResult:
    """Check whether a Telegram user exists and is active in the Personnel sheet."""
    from services.sheets import get_sheets_service

    personnel = get_sheets_service().get_personnel_by_telegram_id(telegram_id)
    if personnel is None:
        return AuthResult(
            allowed=False,
            reason=(
                "شما در لیست پرسنل نیستید.\n"
                f"شناسه تلگرام شما: <code>{telegram_id}</code>\n"
                "لطفاً این شناسه را به مدیر بدهید تا در Google Sheet ثبت شود."
            ),
        )
    if not personnel.active:
        return AuthResult(allowed=False, reason="حساب شما غیرفعال است. با مدیر تماس بگیرید.")
    return AuthResult(allowed=True, personnel=personnel)


def is_admin(personnel: Personnel) -> bool:
    return personnel.role == "admin"


def is_senior_admin(personnel: Personnel) -> bool:
    """True when the Personnel row marks this user as senior manager."""
    return personnel.senior_admin or personnel.role == "senior_admin"


def can_view_all_tasks(personnel: Personnel) -> bool:
    """Senior admin with view_all_tasks enabled can see every assignee's tasks."""
    return is_senior_admin(personnel) and personnel.view_all_tasks


def can_create_tasks(personnel: Personnel) -> bool:
    """Full admin and senior admins may register new tasks."""
    return is_admin(personnel) or is_senior_admin(personnel)


def can_access_filming(personnel: Personnel) -> bool:
    """Access to تصویر برداری is controlled only by the Personnel column flag."""
    return personnel.filming_access


def can_access_content(personnel: Personnel) -> bool:
    """Access to تولید محتوا is controlled only by the Personnel column flag."""
    return personnel.content_access


def enabled_report_kinds(personnel: Personnel) -> tuple[str, ...]:
    """Which chart buttons this person may open. Master flag required."""
    if not personnel.reports_access:
        return ()
    selected = tuple(
        kind
        for kind, enabled in (
            ("status", personnel.report_status),
            ("people", personnel.report_people),
            ("project", personnel.report_project),
            ("deadline", personnel.report_deadline),
            ("month", personnel.report_month),
        )
        if enabled
    )
    if selected:
        kinds = selected
    else:
        kinds = ("status", "people", "project", "deadline", "month")
    if personnel.report_weekly or len(kinds) >= 2:
        return kinds + ("summary",)
    return kinds


def can_access_reports(personnel: Personnel) -> bool:
    return personnel.reports_access


def can_access_report_kind(personnel: Personnel, kind: str) -> bool:
    return kind in enabled_report_kinds(personnel)


def can_update_filming_entry(personnel: Personnel, entry: FilmingEntry) -> bool:
    """Section access plus assignee/creator, or admin."""
    if not can_access_filming(personnel):
        return False
    if is_admin(personnel) or is_senior_admin(personnel):
        return True
    return entry.assignee_name == personnel.name or entry.created_by == personnel.name


def can_update_content_entry(personnel: Personnel, entry: ContentEntry) -> bool:
    """Section access plus named person/creator, or admin."""
    if not can_access_content(personnel):
        return False
    if is_admin(personnel) or is_senior_admin(personnel):
        return True
    return entry.name == personnel.name or entry.created_by == personnel.name
