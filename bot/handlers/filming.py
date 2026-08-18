"""Filming schedule (تصویر برداری) — create / list / status for allowed personnel."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.create_task_flow import safe_answer, safe_edit_text
from bot.formatting import esc
from bot.keyboards import (
    FILMING_TEXTS,
    STATUS_LABELS,
    filming_date_inline_keyboard,
    filming_detail_keyboard,
    filming_list_keyboard,
    filming_menu_keyboard,
    filming_personnel_inline_keyboard,
    filming_projects_inline_keyboard,
    filming_weekday_keyboard,
    main_menu_keyboard,
)
from bot.states import FilmingStates
from services.auth import can_access_filming
from services.sheets import FilmingEntry, Personnel
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="filming")

NO_ACCESS = "دسترسی به بخش تصویر برداری ندارید. از مدیر بخواهید ستون «تصویر برداری» را TRUE کند."


async def _require_filming(message_or_user_id) -> Personnel | None:
    if isinstance(message_or_user_id, int):
        telegram_id = message_or_user_id
        reply = None
    else:
        message = message_or_user_id
        if message.from_user is None:
            return None
        telegram_id = message.from_user.id
        reply = message

    try:
        auth = await authorize(telegram_id)
    except Exception:
        logger.exception("authorize failed in filming")
        if reply is not None:
            await reply.answer("⚠️ اتصال به Google Sheet برقرار نشد.")
        return None
    if not auth.allowed or auth.personnel is None:
        if reply is not None:
            await reply.answer(auth.reason, parse_mode="HTML")
        return None
    if not can_access_filming(auth.personnel):
        if reply is not None:
            await reply.answer(NO_ACCESS)
        return None
    return auth.personnel


def _format_entry(entry: FilmingEntry) -> str:
    return (
        f"🎥 <b>{esc(entry.project)}</b>\n"
        f"📍 محل: {esc(entry.location)}\n"
        f"📆 روز: {esc(entry.day)}\n"
        f"🕐 ساعت: {esc(entry.hour)}\n"
        f"📅 تاریخ: {esc(entry.date)}\n"
        f"👤 مسوول: {esc(entry.assignee_name)}\n"
        f"📊 {esc(STATUS_LABELS.get(entry.status, entry.status))}\n"
        f"✍️ ثبت‌کننده: {esc(entry.created_by)}"
    )


async def _show_filming_menu(message: Message, *, edit: bool = False) -> None:
    sheet_url = await SheetsAsync.get_filming_sheet_url()
    text = (
        "🎥 <b>بخش تصویر برداری</b>\n\n"
        "ثبت و مشاهده برنامه فیلم‌برداری فقط برای افراد مجاز در Personnel."
    )
    markup = filming_menu_keyboard(sheet_url)
    if edit:
        await safe_edit_text(message, text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(F.text.in_(FILMING_TEXTS))
async def filming_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    if await _require_filming(message) is None:
        return
    await _show_filming_menu(message)


@router.callback_query(F.data == "film:menu")
async def filming_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await state.clear()
    if await _require_filming(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return
    await _show_filming_menu(callback.message, edit=True)


@router.callback_query(F.data == "film:cancel")
async def filming_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None or callback.from_user is None:
        return
    personnel = await _require_filming(callback.from_user.id)
    await safe_edit_text(callback.message, "❌ ثبت تصویر برداری لغو شد.")
    if personnel is not None:
        await callback.message.answer(
            "منوی اصلی:",
            reply_markup=main_menu_keyboard(personnel),
        )


@router.callback_query(F.data == "film:new")
async def filming_start_create(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_filming(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return

    projects = await SheetsAsync.get_projects()
    if not projects:
        await callback.message.answer("لیست پروژه خالی است.")
        return

    await state.clear()
    await state.update_data(project_list=projects)
    await state.set_state(FilmingStates.choosing_project)
    await safe_edit_text(
        callback.message,
        "📁 <b>نام پروژه</b> را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=filming_projects_inline_keyboard(projects),
    )


@router.callback_query(F.data.startswith("filmproject:"), FilmingStates.choosing_project)
async def filming_project_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_filming(callback.from_user.id) is None:
        return

    data = await state.get_data()
    projects: list[str] = data.get("project_list", [])
    try:
        index = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.message.answer("پروژه نامعتبر.")
        return
    if index < 0 or index >= len(projects):
        await callback.message.answer("پروژه نامعتبر.")
        return

    await state.update_data(project=projects[index])
    await state.set_state(FilmingStates.entering_location)
    await safe_edit_text(
        callback.message,
        f"📁 پروژه: <b>{esc(projects[index])}</b>\n\n📍 <b>محل فیلم برداری</b> را بنویسید:",
        parse_mode="HTML",
    )


@router.message(FilmingStates.entering_location, F.text)
async def filming_location_entered(message: Message, state: FSMContext) -> None:
    if await _require_filming(message) is None:
        await state.clear()
        return
    location = (message.text or "").strip()
    if len(location) < 2:
        await message.answer("محل باید حداقل ۲ کاراکتر باشد:")
        return
    await state.update_data(location=location)
    await state.set_state(FilmingStates.choosing_day)
    await message.answer("📆 <b>روز</b> را انتخاب کنید:", parse_mode="HTML", reply_markup=filming_weekday_keyboard())


@router.callback_query(F.data.startswith("filmday:"), FilmingStates.choosing_day)
async def filming_day_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_filming(callback.from_user.id) is None:
        return
    day = callback.data.split(":", 1)[1]
    await state.update_data(day=day)
    await state.set_state(FilmingStates.entering_hour)
    await safe_edit_text(
        callback.message,
        f"📆 روز: <b>{esc(day)}</b>\n\n🕐 <b>ساعت</b> را بنویسید (مثلاً ۱۴:۳۰):",
        parse_mode="HTML",
    )


@router.message(FilmingStates.entering_hour, F.text)
async def filming_hour_entered(message: Message, state: FSMContext) -> None:
    if await _require_filming(message) is None:
        await state.clear()
        return
    hour = (message.text or "").strip()
    if len(hour) < 1:
        await message.answer("ساعت را بنویسید:")
        return
    await state.update_data(hour=hour)
    await state.set_state(FilmingStates.choosing_date)
    await message.answer(
        f"🕐 ساعت: <b>{esc(hour)}</b>\n\n📅 <b>تاریخ</b> را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=filming_date_inline_keyboard(),
    )


@router.callback_query(F.data.startswith("filmdate:"), FilmingStates.choosing_date)
async def filming_date_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    if await _require_filming(callback.from_user.id) is None:
        await callback.answer(NO_ACCESS, show_alert=True)
        return

    payload = callback.data.split(":", 1)[1]
    if payload == "manual":
        await callback.answer()
        await state.set_state(FilmingStates.entering_date_manual)
        await safe_edit_text(
            callback.message,
            "✏️ تاریخ شمسی را بنویسید، مثلاً:\n<code>1405/04/09</code>",
            parse_mode="HTML",
        )
        return

    try:
        day_offset = int(payload)
    except ValueError:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    date_str = await SheetsAsync.resolve_shamsi_date_offset(day_offset)
    if date_str is None:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(date=date_str)
    await _ask_assignee(callback.message, state)


@router.message(FilmingStates.entering_date_manual, F.text)
async def filming_date_manual(message: Message, state: FSMContext) -> None:
    if await _require_filming(message) is None:
        await state.clear()
        return
    date_str = await SheetsAsync.validate_shamsi_date(message.text or "")
    if date_str is None:
        await message.answer(
            "فرمت تاریخ نامعتبر است.\nمثال: <code>1405/04/09</code>",
            parse_mode="HTML",
        )
        return
    await state.update_data(date=date_str)
    await _ask_assignee(message, state)


async def _ask_assignee(message: Message, state: FSMContext) -> None:
    employees = await SheetsAsync.get_active_employees()
    if not employees:
        await message.answer("هیچ کارمند فعالی یافت نشد.")
        await state.clear()
        return
    await state.set_state(FilmingStates.choosing_assignee)
    data = await state.get_data()
    await message.answer(
        f"📅 تاریخ: <b>{esc(data.get('date', ''))}</b>\n\n👤 <b>مسوول</b> را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=filming_personnel_inline_keyboard(employees),
    )


@router.callback_query(F.data.startswith("filmassign:"), FilmingStates.choosing_assignee)
async def filming_assignee_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    creator = await _require_filming(callback.from_user.id)
    if creator is None:
        await callback.answer(NO_ACCESS, show_alert=True)
        return

    data = await state.get_data()
    if data.get("film_submitting") or data.get("film_submitted"):
        await callback.answer()
        return

    try:
        telegram_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.answer("مسوول نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال ثبت…")
    await state.update_data(film_submitting=True)

    try:
        assignee = await SheetsAsync.get_personnel_by_telegram_id(telegram_id)
    except Exception:
        logger.exception("filming assignee lookup failed")
        await state.update_data(film_submitting=False)
        await callback.message.answer("⚠️ خطا در خواندن پرسنل.")
        return

    if assignee is None or not assignee.active:
        await state.update_data(film_submitting=False)
        await callback.message.answer("مسوول یافت نشد.")
        return

    project = str(data.get("project", "")).strip()
    location = str(data.get("location", "")).strip()
    day = str(data.get("day", "")).strip()
    hour = str(data.get("hour", "")).strip()
    date_str = str(data.get("date", "")).strip()
    if not all([project, location, day, hour, date_str]):
        await state.clear()
        await callback.message.answer("اطلاعات ناقص است. دوباره از منوی تصویر برداری شروع کنید.")
        return

    try:
        entry = await SheetsAsync.create_filming_entry(
            project=project,
            location=location,
            day=day,
            hour=hour,
            date=date_str,
            assignee=assignee,
            created_by_name=creator.name,
        )
    except Exception:
        logger.exception("create_filming_entry failed")
        await state.update_data(film_submitting=False)
        await callback.message.answer("⚠️ ثبت در شیت ناموفق بود. چند ثانیه بعد دوباره تلاش کنید.")
        return

    await state.update_data(film_submitted=True)
    await state.clear()

    await safe_edit_text(
        callback.message,
        f"✅ در شیت تصویر برداری ثبت شد!\n\n{_format_entry(entry)}",
        parse_mode="HTML",
    )
    await callback.message.answer("منوی اصلی:", reply_markup=main_menu_keyboard(creator))

    try:
        await callback.message.bot.send_message(
            assignee.telegram_id,
            f"🎥 <b>برنامه تصویر برداری جدید</b>\n\n{_format_entry(entry)}",
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("filming notify failed for %s", assignee.telegram_id, exc_info=True)
        await safe_answer(
            callback.message,
            f"⚠️ ثبت شد، ولی اعلان به <b>{esc(assignee.name)}</b> ارسال نشد.",
            parse_mode="HTML",
        )


@router.callback_query(F.data == "film:list")
async def filming_list(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await state.clear()
    if await _require_filming(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return

    entries = await SheetsAsync.list_filming_entries(status=None)
    await safe_edit_text(
        callback.message,
        f"📋 برنامه تصویر برداری باز ({len(entries)} مورد):",
        reply_markup=filming_list_keyboard(entries),
    )


@router.callback_query(F.data.startswith("film:view:"))
async def filming_view(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    personnel = await _require_filming(callback.from_user.id)
    if personnel is None:
        await callback.message.answer(NO_ACCESS)
        return

    entry_id = callback.data.removeprefix("film:view:")
    entry = await SheetsAsync.get_filming_entry_by_id(entry_id)
    if entry is None:
        await callback.message.answer("مورد یافت نشد.")
        return

    can_update = can_access_filming(personnel)
    await safe_edit_text(
        callback.message,
        _format_entry(entry),
        parse_mode="HTML",
        reply_markup=filming_detail_keyboard(
            entry.id,
            can_update=can_update,
            status=entry.status,
        ),
    )


@router.callback_query(F.data.startswith("film:status:"))
async def filming_status(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    personnel = await _require_filming(callback.from_user.id)
    if personnel is None:
        await callback.answer(NO_ACCESS, show_alert=True)
        return

    payload = callback.data.removeprefix("film:status:")
    entry_id, new_status = payload.rsplit(":", 1)
    if new_status not in {"in_progress", "done", "cancelled"}:
        await callback.answer("وضعیت نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال به‌روزرسانی…")
    updated = await SheetsAsync.update_filming_status(entry_id, personnel, new_status)
    if not updated:
        await callback.message.answer("⚠️ به‌روزرسانی ناموفق بود.")
        return

    entry = await SheetsAsync.get_filming_entry_by_id(entry_id)
    if entry is None:
        await callback.message.answer("مورد یافت نشد.")
        return

    can_update = can_access_filming(personnel)
    await safe_edit_text(
        callback.message,
        _format_entry(entry),
        parse_mode="HTML",
        reply_markup=filming_detail_keyboard(
            entry.id,
            can_update=can_update,
            status=entry.status,
        ),
    )
