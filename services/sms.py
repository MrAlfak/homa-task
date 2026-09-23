"""mydnspanel SMS client and personnel notify helpers."""

from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from html import unescape
from typing import Any

import requests

from services.sheets_models import (
    ContentEntry,
    FilmingEntry,
    Personnel,
    SmsSettings,
    Task,
    normalize_mobile,
)

logger = logging.getLogger(__name__)

SMS_API_URL = "https://mydnspanel.com/webservice/server"
_TIMEOUT_SEC = 20
_HTML_TAG_RE = re.compile(r"<[^>]+>")
_logged_missing_key = False


@dataclass(frozen=True)
class SmsSendResult:
    ok: bool
    send_id: str = ""
    result_code: str = ""
    description: str = ""
    skipped: bool = False


def html_to_plain(text: str) -> str:
    cleaned = (text or "").replace("\r\n", "\n")
    cleaned = re.sub(r"<br\s*/?>", "\n", cleaned, flags=re.I)
    cleaned = re.sub(r"</p>", "\n", cleaned, flags=re.I)
    cleaned = _HTML_TAG_RE.sub("", cleaned)
    cleaned = unescape(cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def format_new_task_sms(task: Task, *, creator_name: str) -> str:
    return (
        "تسک جدید\n"
        f"عنوان: {task.title}\n"
        f"پروژه: {task.project}\n"
        f"اولویت: {task.priority}\n"
        f"از طرف: {creator_name}\n"
        f"ددلاین: {task.due_date}"
    )


def format_overdue_sms(tasks: Sequence[Task]) -> str:
    lines = ["تسک‌های عقب‌افتاده"]
    for task in list(tasks)[:8]:
        lines.append(f"- {task.title} | {task.project} | {task.due_date}")
    extra = len(tasks) - 8
    if extra > 0:
        lines.append(f"و {extra} مورد دیگر")
    lines.append("وضعیت را در ربات به‌روز کنید.")
    return "\n".join(lines)


def format_announce_sms() -> str:
    return (
        "ربات مدیریت تسک بروزرسانی شد.\n"
        "جزئیات را در تلگرام ببینید و یک‌بار /start بزنید."
    )


def format_filming_sms(entry: FilmingEntry) -> str:
    return (
        "برنامه تصویربرداری جدید\n"
        f"پروژه: {entry.project}\n"
        f"محل: {entry.location}\n"
        f"روز: {entry.day}\n"
        f"ساعت: {entry.hour}\n"
        f"تاریخ: {entry.date}"
    )


def format_content_sms(entry: ContentEntry) -> str:
    kinds = []
    if entry.post.strip():
        kinds.append("پست")
    if entry.story.strip():
        kinds.append("استوری")
    kind = " و ".join(kinds) or "دیزاین"
    return (
        "دیزاین / تولید محتوا جدید\n"
        f"نام: {entry.name}\n"
        f"پروژه: {entry.project}\n"
        f"نوع: {kind}"
    )


def _result_ok(value: Any) -> bool:
    cleaned = str(value or "").strip().lower()
    return cleaned in {"1", "true", "ok", "success"}


def _extract_send_id(payload: Any) -> str:
    if isinstance(payload, dict):
        for key in ("sendID", "sendId", "id"):
            raw = payload.get(key)
            if raw not in (None, ""):
                return str(raw)
        data = payload.get("data")
        if data is not None and data is not payload:
            return _extract_send_id(data)
    return ""


def post_sms(
    *,
    api_key: str,
    sender: str,
    receivers: str,
    text: str,
    send_type: int = 1,
    try_send: int = 2,
    text_code: str = "",
    text_data: list[str] | None = None,
    api_url: str = SMS_API_URL,
) -> SmsSendResult:
    """POST to mydnspanel. Never raises; returns a structured result."""
    if not api_key.strip() or not receivers.strip() or not (text.strip() or text_code.strip()):
        return SmsSendResult(ok=False, skipped=True, description="missing key/receivers/text")

    data: dict[str, str] = {
        "from": sender.strip() or "auto",
        "receivers": receivers.strip(),
        "trySend": str(max(0, min(10, try_send))),
        "type": str(send_type or 1),
    }
    if text_code.strip():
        data["action"] = "sendServices"
        data["textCode"] = text_code.strip()
        for index, item in enumerate(text_data or []):
            data[f"textData[{index}]"] = item
    else:
        data["action"] = "send"
        data["text"] = text

    try:
        response = requests.post(
            api_url,
            data=data,
            headers={"Authorization": api_key.strip()},
            timeout=_TIMEOUT_SEC,
        )
    except Exception as extra:  # noqa: BLE001
        logger.warning("SMS HTTP failed: %s: %s", type(extra).__name__, extra)
        return SmsSendResult(ok=False, description=f"{type(extra).__name__}")

    body: Any
    try:
        body = response.json()
    except ValueError:
        snippet = (response.text or "")[:180]
        return SmsSendResult(
            ok=False,
            result_code=str(response.status_code),
            description=snippet or f"HTTP {response.status_code}",
        )

    if isinstance(body, dict):
        code = str(body.get("result", ""))
        description = str(body.get("description", body.get("message", ""))).strip()
        return SmsSendResult(
            ok=_result_ok(code),
            send_id=_extract_send_id(body),
            result_code=code,
            description=description or ("ok" if _result_ok(code) else "send failed"),
        )
    return SmsSendResult(ok=False, description=str(body)[:180])


def _event_enabled(settings: SmsSettings, event: str) -> bool:
    if event in {"new_task", "filming", "content"}:
        return settings.on_new_task
    if event == "overdue":
        return settings.on_overdue
    if event == "announce":
        return settings.on_announce
    return False


def _pattern_for(settings: SmsSettings, event: str) -> str:
    if event in {"new_task", "filming", "content"}:
        return settings.pattern_new_task
    if event == "overdue":
        return settings.pattern_overdue
    if event == "announce":
        return settings.pattern_announce
    return ""


def _sms_targets(people: Sequence[Personnel]) -> list[tuple[Personnel, str]]:
    targets: list[tuple[Personnel, str]] = []
    seen: set[str] = set()
    for person in people:
        if not person.sms_enabled:
            continue
        mobile = normalize_mobile(person.mobile)
        if not mobile or mobile in seen:
            continue
        seen.add(mobile)
        targets.append((person, mobile))
    return targets


def skip_reason_for_person(person: Personnel, *, seen_mobiles: set[str] | None = None) -> str:
    """Why this person would not get an SMS. Empty string means they are a target."""
    if not person.sms_enabled:
        return "ارسال پیامک=FALSE"
    mobile = normalize_mobile(person.mobile)
    if not mobile:
        return "شماره موبایل خالی یا نامعتبر"
    if seen_mobiles is not None and mobile in seen_mobiles:
        return "شماره تکراری"
    return ""


async def _append_sms_log(
    *,
    name: str,
    mobile: str,
    kind: str,
    text: str,
    send_id: str = "",
    status: str,
    detail: str = "",
) -> None:
    from services.sheets_async import SheetsAsync

    try:
        await SheetsAsync.append_sms_log(
            name=name,
            mobile=mobile,
            kind=kind,
            text=text,
            send_id=send_id,
            status=status,
            detail=detail,
        )
    except Exception:
        logger.warning("SMS log write failed", exc_info=True)


async def _guard(coro: Any) -> None:
    try:
        await coro
    except Exception:
        logger.exception("SMS notify task crashed")


def schedule(coro: Any) -> None:
    """Run SMS in the background; never block the caller on panel latency."""
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        logger.warning("SMS skipped: no running event loop")
        return
    loop.create_task(_guard(coro), name="sms-notify")


async def notify_people(
    *,
    event: str,
    people: Sequence[Personnel],
    text: str,
    pattern_vars: list[str] | None = None,
) -> int:
    """Send SMS to opted-in personnel. Returns number of successful recipients."""
    global _logged_missing_key
    from config import config
    from services.sheets_async import SheetsAsync

    api_key = config.sms_api_key
    if not api_key:
        if not _logged_missing_key:
            logger.info("SMS skipped: SMS_API_KEY is not set")
            _logged_missing_key = True
        for person in people:
            await _append_sms_log(
                name=person.name,
                mobile=normalize_mobile(person.mobile),
                kind=event,
                text=text,
                status="skip",
                detail="SMS_API_KEY روی سرور تنظیم نشده",
            )
        return 0

    try:
        settings = await SheetsAsync.get_sms_settings()
    except Exception:
        logger.exception("SMS settings read failed")
        for person in people:
            await _append_sms_log(
                name=person.name,
                mobile=normalize_mobile(person.mobile),
                kind=event,
                text=text,
                status="skip",
                detail="خواندن تنظیمات تب SMS ناموفق بود",
            )
        return 0

    if not settings.enabled or not _event_enabled(settings, event):
        detail = (
            "فعال=FALSE در تب SMS"
            if not settings.enabled
            else f"رویداد {event} در تب SMS خاموش است"
        )
        logger.info("SMS skipped: %s", detail)
        for person in people:
            await _append_sms_log(
                name=person.name,
                mobile=normalize_mobile(person.mobile),
                kind=event,
                text=text,
                status="skip",
                detail=detail,
            )
        return 0

    targets = _sms_targets(people)
    if not targets:
        seen: set[str] = set()
        logger.info("SMS skipped: no valid mobile targets for event=%s", event)
        for person in people:
            reason = skip_reason_for_person(person, seen_mobiles=seen)
            mobile = normalize_mobile(person.mobile)
            if person.sms_enabled and mobile:
                seen.add(mobile)
            await _append_sms_log(
                name=person.name,
                mobile=mobile,
                kind=event,
                text=text,
                status="skip",
                detail=reason or "گیرنده معتبر نیست",
            )
        return 0

    pattern = _pattern_for(settings, event)
    sent = 0

    async def _one(person: Personnel, mobile: str, body: str, vars_: list[str] | None) -> bool:
        result = await asyncio.to_thread(
            post_sms,
            api_key=api_key,
            api_url=config.sms_api_url,
            sender=settings.sender,
            receivers=mobile,
            text=body,
            send_type=settings.send_type,
            try_send=settings.try_send,
            text_code=pattern,
            text_data=vars_,
        )
        fallback_used = False
        pattern_error = ""
        if pattern and not result.ok and not result.skipped:
            pattern_error = result.description or result.result_code or "خطا در ارسال پترن"
            logger.warning(
                "Pattern SMS failed for %s (%s); trying plain text fallback...",
                person.name,
                pattern_error,
            )
            fallback_res = await asyncio.to_thread(
                post_sms,
                api_key=api_key,
                api_url=config.sms_api_url,
                sender=settings.sender,
                receivers=mobile,
                text=body,
                send_type=settings.send_type,
                try_send=settings.try_send,
            )
            result = fallback_res
            fallback_used = True

        status = "ok" if result.ok else "fail"
        detail = result.description or result.result_code
        if fallback_used:
            detail = f"پترن ناموفق ({pattern_error}) -> متن ساده: {detail}"

        await _append_sms_log(
            name=person.name,
            mobile=mobile,
            kind=event,
            text=body,
            send_id=result.send_id,
            status=status,
            detail=detail,
        )
        if result.ok:
            logger.info("SMS sent event=%s name=%s", event, person.name)
        else:
            logger.warning(
                "SMS failed event=%s name=%s code=%s detail=%s",
                event,
                person.name,
                result.result_code,
                result.description,
            )
        return result.ok

    can_batch = event == "announce" and not pattern and len(targets) > 1
    if can_batch:
        receivers = ",".join(mobile for _person, mobile in targets)
        result = await asyncio.to_thread(
            post_sms,
            api_key=api_key,
            api_url=config.sms_api_url,
            sender=settings.sender,
            receivers=receivers,
            text=text,
            send_type=settings.send_type,
            try_send=settings.try_send,
        )
        for person, mobile in targets:
            await _append_sms_log(
                name=person.name,
                mobile=mobile,
                kind=event,
                text=text,
                send_id=result.send_id,
                status="ok" if result.ok else "fail",
                detail=result.description or result.result_code,
            )
        return len(targets) if result.ok else 0

    for person, mobile in targets:
        vars_ = list(pattern_vars or [])
        if person.name and (not vars_ or vars_[0] != person.name):
            vars_ = [person.name, *vars_]
        if await _one(person, mobile, text, vars_ if pattern else None):
            sent += 1
        await asyncio.sleep(0.05)
    return sent


async def notify_new_task(person: Personnel | None, task: Task, creator_name: str) -> int:
    if person is None:
        return 0
    return await notify_people(
        event="new_task",
        people=[person],
        text=format_new_task_sms(task, creator_name=creator_name),
        pattern_vars=[task.title, task.project, task.priority, creator_name, task.due_date],
    )


async def notify_overdue(person: Personnel, tasks: Sequence[Task]) -> int:
    return await notify_people(
        event="overdue",
        people=[person],
        text=format_overdue_sms(tasks),
        pattern_vars=[person.name, format_overdue_sms(tasks)],
    )


async def notify_announce(people: Sequence[Personnel]) -> int:
    return await notify_people(
        event="announce",
        people=people,
        text=format_announce_sms(),
    )


async def notify_filming(person: Personnel | None, entry: FilmingEntry) -> int:
    if person is None:
        return 0
    return await notify_people(
        event="filming",
        people=[person],
        text=format_filming_sms(entry),
        pattern_vars=[entry.project, entry.location, entry.day, entry.hour, entry.date],
    )


async def notify_content(person: Personnel | None, entry: ContentEntry) -> int:
    if person is None:
        return 0
    return await notify_people(
        event="content",
        people=[person],
        text=format_content_sms(entry),
        pattern_vars=[entry.name, entry.project, entry.content_type],
    )
