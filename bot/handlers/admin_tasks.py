"""Admin: create task flow — matches Google Sheet structure."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.create_task_flow import (
    ASSIGNEE_NOTIFY_FAILED_TEXT,
    FLOW_EXPIRED_TEXT,
    INCOMPLETE_DATA_TEXT,
    SHEETS_ERROR_TEXT,
    run_sheets_step,
    safe_answer,
    safe_edit_text,
)
from bot.formatting import esc
from bot.keyboards import (
    CREATE_TASK_TEXTS,
    due_date_inline_keyboard,
    personnel_inline_keyboard,
    priority_inline_keyboard,
    projects_inline_keyboard,
)
from bot.states import CreateTaskStates
from services.auth import can_create_tasks
from services.sheets import Personnel
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="admin_tasks")


async def _require_task_creator_message(message: Message) -> Personnel | None:
    if message.from_user is None:
        return None
    try:
        auth = await authorize(message.from_user.id)
    except Exception:
        logger.exception("authorize failed in create-task (message)")
        await message.answer(SHEETS_ERROR_TEXT)
        return None
    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return None
    if not can_create_tasks(auth.personnel):
        await message.answer("فقط مدیر یا مدیر ارشد می‌تواند تسک ثبت کند.")
        return None
    return auth.personnel


async def _require_task_creator_callback(callback: CallbackQuery) -> Personnel | None:
    if callback.from_user is None or callback.message is None:
        return None
    try:
        auth = await authorize(callback.from_user.id)
    except Exception:
        logger.exception("authorize failed in create-task (callback)")
        await callback.message.answer(SHEETS_ERROR_TEXT)
        return None
    if not auth.allowed or auth.personnel is None or not can_create_tasks(auth.personnel):
        await callback.message.answer("دسترسی ندارید.")
        return None
    return auth.personnel


async def _lookup_employee(message: Message, telegram_id: int) -> Personnel | None:
    """Return employee, None if missing, or abort flow on Sheets error."""
    try:
        employee = await SheetsAsync.get_personnel_by_telegram_id(telegram_id, role="employee")
    except Exception:
        logger.exception("get_personnel_by_telegram_id failed for %s", telegram_id)
        await message.answer(SHEETS_ERROR_TEXT)
        return None
    if employee is None:
        await message.answer("کارمند یافت نشد.")
    return employee


@router.message(F.text.in_(CREATE_TASK_TEXTS))
async def start_create_task(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    await state.clear()
    await message.answer("⏳ در حال بارگذاری لیست کارمندان…")

    if await _require_task_creator_message(message) is None:
        return

    employees = await run_sheets_step(message, "get_active_employees", SheetsAsync.get_active_employees())
    if employees is None:
        return
    if not employees:
        await message.answer(
            "هیچ کارمند فعالی در تب Personnel یافت نشد.\n"
            "کارمند با role=employee و active=TRUE اضافه کنید."
        )
        return

    await state.set_state(CreateTaskStates.choosing_employee)
    await message.answer(
        "👤 مسئول تسک را انتخاب کنید:",
        reply_markup=personnel_inline_keyboard(employees),
    )


@router.callback_query(F.data.startswith("assign:"), CreateTaskStates.choosing_employee)
async def employee_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    if await _require_task_creator_callback(callback) is None:
        return

    try:
        telegram_id = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        await callback.message.answer("کارمند نامعتبر.")
        return

    employee = await _lookup_employee(callback.message, telegram_id)
    if employee is None:
        return

    projects = await run_sheets_step(callback.message, "get_projects", SheetsAsync.get_projects())
    if projects is None:
        return
    if not projects:
        await callback.message.answer("لیست پروژه خالی است.")
        return

    await state.update_data(
        assignee_id=employee.telegram_id,
        assignee_name=employee.name,
        project_list=projects,
    )
    await state.set_state(CreateTaskStates.choosing_project)
    await safe_edit_text(
        callback.message,
        f"👤 مسئول: <b>{esc(employee.name)}</b>\n\n"
        "📁 <b>پروژه</b> را انتخاب کنید:\n"
        "🌐 = کار چندپروژه‌ای (مثل آپلودها)\n"
        "📁 = پروژه/پیج مشخص",
        parse_mode="HTML",
        reply_markup=projects_inline_keyboard(projects),
    )


@router.callback_query(F.data.startswith("projectidx:"), CreateTaskStates.choosing_project)
async def project_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    await callback.answer()

    if await _require_task_creator_callback(callback) is None:
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

    project = projects[index]
    await state.update_data(project=project)
    await state.set_state(CreateTaskStates.entering_title)
    await safe_edit_text(
        callback.message,
        f"📁 پروژه: <b>{esc(project)}</b>\n\n📌 عنوان تسک را بنویسید:",
        parse_mode="HTML",
    )


@router.message(CreateTaskStates.entering_title, F.text)
async def receive_title(message: Message, state: FSMContext) -> None:
    if await _require_task_creator_message(message) is None:
        await state.clear()
        return

    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("عنوان باید حداقل ۲ کاراکتر باشد:")
        return

    await state.update_data(title=title)
    await state.set_state(CreateTaskStates.choosing_priority)
    await message.answer("⚡ اولویت را انتخاب کنید:", reply_markup=priority_inline_keyboard())


@router.callback_query(F.data.startswith("priority:"), CreateTaskStates.choosing_priority)
async def priority_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    await callback.answer()

    if await _require_task_creator_callback(callback) is None:
        return

    priority = callback.data.split(":", 1)[1]
    await state.update_data(priority=priority)
    await state.set_state(CreateTaskStates.choosing_due_date)
    await safe_edit_text(
        callback.message,
        f"⚡ اولویت: <b>{esc(priority)}</b>\n\n📅 ددلاین را انتخاب کنید:",
        parse_mode="HTML",
        reply_markup=due_date_inline_keyboard(),
    )


@router.callback_query(F.data.startswith("duedate:"), CreateTaskStates.choosing_due_date)
async def due_date_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    if await _require_task_creator_callback(callback) is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    payload = callback.data.split(":", 1)[1]
    if payload == "manual":
        await callback.answer()
        await state.set_state(CreateTaskStates.entering_due_date_manual)
        await safe_edit_text(
            callback.message,
            "✏️ <b>ورود دستی ددلاین</b>\n\n"
            "تاریخ شمسی را بنویسید (۱۵ روز قبل تا ۱۵ روز بعد، یا هر تاریخ معتبر)، مثلاً:\n"
            "<code>1405/04/09</code>",
            parse_mode="HTML",
        )
        return

    try:
        day_offset = int(payload)
    except ValueError:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    due_date = await SheetsAsync.resolve_shamsi_date_offset(day_offset)
    if due_date is None:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال ثبت تسک…")
    await state.update_data(due_date=due_date)
    await _finalize_task(callback.message, callback.from_user, state)


@router.message(CreateTaskStates.entering_due_date_manual, F.text)
async def receive_due_date_manual(message: Message, state: FSMContext) -> None:
    if await _require_task_creator_message(message) is None:
        await state.clear()
        return

    if message.text and message.text.strip().startswith("/"):
        await state.clear()
        await message.answer("❌ ثبت تسک لغو شد.")
        return

    due_date = await SheetsAsync.validate_shamsi_date(message.text or "")
    if due_date is None:
        await message.answer(
            "فرمت تاریخ نامعتبر است.\n"
            "مثال: <code>1405/04/09</code>\n\n"
            "دوباره بنویسید یا «❌ انصراف» را در پیام قبلی بزنید.",
            parse_mode="HTML",
        )
        return

    await message.answer("⏳ در حال ثبت تسک…")
    await state.update_data(due_date=due_date)
    if message.from_user is None:
        return
    await _finalize_task(message, message.from_user, state)


async def _finalize_task(message: Message | None, from_user, state: FSMContext) -> None:
    if message is None or from_user is None:
        return

    data = await state.get_data()
    if data.get("task_submitting") or data.get("task_submitted"):
        return

    try:
        auth = await authorize(from_user.id)
    except Exception:
        logger.exception("authorize failed during task finalize")
        await safe_answer(message, SHEETS_ERROR_TEXT)
        return

    if not auth.allowed or auth.personnel is None or not can_create_tasks(auth.personnel):
        await state.clear()
        return

    assignee_id = data.get("assignee_id")
    title = data.get("title", "")
    project = data.get("project", "")
    priority = data.get("priority", "Medium")
    due_date = data.get("due_date", "")

    if not assignee_id or not title or not project:
        await safe_answer(message, INCOMPLETE_DATA_TEXT)
        await state.clear()
        return

    await state.update_data(task_submitting=True)

    assignee = await _lookup_employee(message, int(assignee_id))
    if assignee is None:
        await state.update_data(task_submitting=False)
        await state.clear()
        return

    try:
        task = await SheetsAsync.create_task(
            title=title,
            project=project,
            assignee=assignee,
            created_by_name=auth.personnel.name,
            priority=priority,
            due_date=due_date,
        )
    except Exception:
        logger.exception("create_task failed")
        await state.update_data(task_submitting=False)
        await safe_answer(
            message,
            "⚠️ ثبت تسک در Google Sheet ناموفق بود. لطفاً چند ثانیه بعد دوباره «➕ ثبت تسک جدید» را بزنید.",
        )
        return

    await state.update_data(task_submitted=True)
    await state.clear()

    success_text = (
        f"✅ تسک در Google Sheet ثبت شد!\n\n"
        f"📌 {esc(task.title)}\n"
        f"📁 {esc(task.project)}\n"
        f"👤 مسئول: {esc(assignee.name)}\n"
        f"⚡ {esc(task.priority)}\n"
        f"📅 تاریخ ایجاد: {esc(task.created_at)}\n"
        f"📅 ددلاین: {esc(task.due_date)}"
    )
    if not await safe_answer(message, success_text, parse_mode="HTML"):
        await safe_answer(message, "✅ تسک در Google Sheet ثبت شد.")

    try:
        await message.bot.send_message(
            assignee.telegram_id,
            f"📌 <b>تسک جدید</b>\n\n"
            f"📋 {esc(task.title)}\n"
            f"📁 {esc(task.project)}\n"
            f"⚡ {esc(task.priority)}\n"
            f"👤 از طرف: {esc(auth.personnel.name)}\n"
            f"📅 ددلاین: {esc(task.due_date)}",
            parse_mode="HTML",
        )
    except Exception:
        logger.warning("assignee notify failed for %s", assignee.telegram_id, exc_info=True)
        await safe_answer(
            message,
            ASSIGNEE_NOTIFY_FAILED_TEXT.format(name=esc(assignee.name)),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cancel:create_task")
async def cancel_create_task(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text("❌ ثبت تسک لغو شد.")


@router.callback_query(
    F.data.startswith("assign:")
    | F.data.startswith("projectidx:")
    | F.data.startswith("priority:")
    | F.data.startswith("duedate:")
)
async def create_task_stale_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Recover when inline buttons are tapped after FSM state was lost (e.g. bot restart)."""
    if callback.message is None:
        return

    await callback.answer()
    await state.clear()
    await safe_answer(callback.message, FLOW_EXPIRED_TEXT)
