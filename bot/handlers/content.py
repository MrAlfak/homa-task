"""Design / تولید محتوا — create / list / status for allowed personnel."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.create_task_flow import safe_answer, safe_edit_text
from bot.formatting import esc
from bot.keyboards import (
    CONTENT_TEXTS,
    STATUS_LABELS,
    content_detail_keyboard,
    content_list_keyboard,
    content_menu_keyboard,
    content_person_keyboard,
    content_projects_inline_keyboard,
    content_type_keyboard,
    main_menu_keyboard,
)
from bot.states import ContentStates
from services.auth import can_access_content
from services.sheets import ContentEntry, Personnel
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="content")

NO_ACCESS = "دسترسی به بخش تولید محتوا ندارید. از مدیر بخواهید ستون «تولید محتوا» را TRUE کند."


async def _require_content(message_or_user_id) -> Personnel | None:
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
        logger.exception("authorize failed in content")
        if reply is not None:
            await reply.answer("⚠️ اتصال به Google Sheet برقرار نشد.")
        return None
    if not auth.allowed or auth.personnel is None:
        if reply is not None:
            await reply.answer(auth.reason, parse_mode="HTML")
        return None
    if not can_access_content(auth.personnel):
        if reply is not None:
            await reply.answer(NO_ACCESS)
        return None
    return auth.personnel


def _format_entry(entry: ContentEntry) -> str:
    post_line = "✓" if entry.post.strip() else "—"
    story_line = "✓" if entry.story.strip() else "—"
    return (
        f"✍️ <b>{esc(entry.name or '—')}</b>\n"
        f"📁 پروژه: {esc(entry.project or '—')}\n"
        f"📰 پست: {esc(post_line)}\n"
        f"📱 استوری: {esc(story_line)}\n"
        f"📊 {esc(STATUS_LABELS.get(entry.status, entry.status))}\n"
        f"✍️ ثبت‌کننده: {esc(entry.created_by)}"
    )


async def _show_content_menu(message: Message, *, edit: bool = False) -> None:
    sheet_url = await SheetsAsync.get_content_sheet_url()
    text = (
        "✍️ <b>بخش تولید محتوا (Design)</b>\n\n"
        "ثبت روی تب Design با ستون‌های نام / پروژه / پست / استوری."
    )
    markup = content_menu_keyboard(sheet_url)
    if edit:
        await safe_edit_text(message, text, parse_mode="HTML", reply_markup=markup)
    else:
        await message.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(F.text.in_(CONTENT_TEXTS))
async def content_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    if await _require_content(message) is None:
        return
    await _show_content_menu(message)


@router.callback_query(F.data == "content:menu")
async def content_menu_callback(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await state.clear()
    if await _require_content(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return
    await _show_content_menu(callback.message, edit=True)


@router.callback_query(F.data == "content:cancel")
async def content_cancel(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message is None or callback.from_user is None:
        return
    personnel = await _require_content(callback.from_user.id)
    await safe_edit_text(callback.message, "❌ ثبت تولید محتوا لغو شد.")
    if personnel is not None:
        await callback.message.answer(
            "منوی اصلی:",
            reply_markup=main_menu_keyboard(personnel),
        )


@router.callback_query(F.data == "content:new")
async def content_start_create(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_content(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return

    names = await SheetsAsync.get_design_names()
    if not names:
        await callback.message.answer("لیست نام‌های Design خالی است.")
        return

    await state.clear()
    await state.update_data(person_list=names)
    await state.set_state(ContentStates.choosing_person)
    await safe_edit_text(
        callback.message,
        "👤 <b>نام</b> را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=content_person_keyboard(names),
    )


@router.callback_query(F.data.startswith("contentperson:"), ContentStates.choosing_person)
async def content_person_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_content(callback.from_user.id) is None:
        return

    data = await state.get_data()
    names: list[str] = data.get("person_list", [])
    try:
        index = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.message.answer("نام نامعتبر.")
        return
    if index < 0 or index >= len(names):
        await callback.message.answer("نام نامعتبر.")
        return

    projects = await SheetsAsync.get_projects()
    if not projects:
        await callback.message.answer("لیست پروژه خالی است.")
        return

    await state.update_data(person_name=names[index], project_list=projects)
    await state.set_state(ContentStates.choosing_project)
    await safe_edit_text(
        callback.message,
        f"👤 نام: <b>{esc(names[index])}</b>\n\n📁 <b>پروژه</b> را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=content_projects_inline_keyboard(projects),
    )


@router.callback_query(F.data.startswith("contentproject:"), ContentStates.choosing_project)
async def content_project_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    if await _require_content(callback.from_user.id) is None:
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
    await state.set_state(ContentStates.choosing_type)
    await safe_edit_text(
        callback.message,
        f"📁 پروژه: <b>{esc(projects[index])}</b>\n\n📰 <b>پست / استوری</b>؟",
        parse_mode="HTML",
        reply_markup=content_type_keyboard(),
    )


@router.callback_query(F.data.startswith("contenttype:"), ContentStates.choosing_type)
async def content_type_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    creator = await _require_content(callback.from_user.id)
    if creator is None:
        await callback.answer(NO_ACCESS, show_alert=True)
        return

    data = await state.get_data()
    if data.get("content_submitting") or data.get("content_submitted"):
        await callback.answer()
        return

    choice = callback.data.split(":", 1)[1]
    include_post = choice in {"post", "both"}
    include_story = choice in {"story", "both"}
    if not include_post and not include_story:
        await callback.answer("نوع نامعتبر.", show_alert=True)
        return

    person_name = str(data.get("person_name", "")).strip()
    project = str(data.get("project", "")).strip()
    if not person_name or not project:
        await state.clear()
        await callback.message.answer("اطلاعات ناقص است. دوباره از منوی تولید محتوا شروع کنید.")
        return

    await callback.answer("در حال ثبت…")
    await state.update_data(content_submitting=True)

    try:
        entry = await SheetsAsync.create_content_entry(
            name=person_name,
            project=project,
            include_post=include_post,
            include_story=include_story,
            created_by_name=creator.name,
        )
    except Exception:
        logger.exception("create_content_entry failed")
        await state.update_data(content_submitting=False)
        await callback.message.answer("⚠️ ثبت در شیت ناموفق بود. چند ثانیه بعد دوباره تلاش کنید.")
        return

    await state.update_data(content_submitted=True)
    await state.clear()

    await safe_edit_text(
        callback.message,
        f"✅ در شیت Design ثبت شد!\n\n{_format_entry(entry)}",
        parse_mode="HTML",
    )
    await callback.message.answer("منوی اصلی:", reply_markup=main_menu_keyboard(creator))

    try:
        assignee = await SheetsAsync.find_personnel_by_name_hint(person_name)
    except Exception:
        logger.warning("content assignee lookup failed for %s", person_name, exc_info=True)
        assignee = None

    if assignee is not None:
        try:
            await callback.message.bot.send_message(
                assignee.telegram_id,
                f"✍️ <b>دیزاین / تولید محتوا جدید</b>\n\n{_format_entry(entry)}",
                parse_mode="HTML",
            )
        except Exception:
            logger.warning("content notify failed for %s", assignee.telegram_id, exc_info=True)
            await safe_answer(
                callback.message,
                f"⚠️ ثبت شد، ولی اعلان به <b>{esc(assignee.name)}</b> ارسال نشد.",
                parse_mode="HTML",
            )


@router.callback_query(F.data == "content:list")
async def content_list(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    await state.clear()
    if await _require_content(callback.from_user.id) is None:
        await callback.message.answer(NO_ACCESS)
        return

    entries = await SheetsAsync.list_content_entries(status=None)
    await safe_edit_text(
        callback.message,
        f"📋 دیزاین باز ({len(entries)} مورد):",
        reply_markup=content_list_keyboard(entries),
    )


@router.callback_query(F.data.startswith("content:view:"))
async def content_view(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    personnel = await _require_content(callback.from_user.id)
    if personnel is None:
        await callback.message.answer(NO_ACCESS)
        return

    entry_id = callback.data.removeprefix("content:view:")
    entry = await SheetsAsync.get_content_entry_by_id(entry_id)
    if entry is None:
        await callback.message.answer("مورد یافت نشد.")
        return

    await safe_edit_text(
        callback.message,
        _format_entry(entry),
        parse_mode="HTML",
        reply_markup=content_detail_keyboard(
            entry.id,
            can_update=can_access_content(personnel),
            status=entry.status,
        ),
    )


@router.callback_query(F.data.startswith("content:status:"))
async def content_status(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    personnel = await _require_content(callback.from_user.id)
    if personnel is None:
        await callback.answer(NO_ACCESS, show_alert=True)
        return

    payload = callback.data.removeprefix("content:status:")
    entry_id, new_status = payload.rsplit(":", 1)
    if new_status not in {"in_progress", "done", "cancelled"}:
        await callback.answer("وضعیت نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال به‌روزرسانی…")
    updated = await SheetsAsync.update_content_status(entry_id, personnel, new_status)
    if not updated:
        await callback.message.answer("⚠️ به‌روزرسانی ناموفق بود.")
        return

    entry = await SheetsAsync.get_content_entry_by_id(entry_id)
    if entry is None:
        await callback.message.answer("مورد یافت نشد.")
        return

    await safe_edit_text(
        callback.message,
        _format_entry(entry),
        parse_mode="HTML",
        reply_markup=content_detail_keyboard(
            entry.id,
            can_update=can_access_content(personnel),
            status=entry.status,
        ),
    )
