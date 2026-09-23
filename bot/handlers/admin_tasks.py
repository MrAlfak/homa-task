"""Admin: create task flow — matches Google Sheet structure."""

from __future__ import annotations

import asyncio
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
    REPLY_MENU_TEXTS,
    cancel_flow_keyboard,
    due_date_inline_keyboard,
    personnel_inline_keyboard,
    priority_inline_keyboard,
    projects_inline_keyboard,
    task_confirm_inline_keyboard,
)
from bot.states import CreateTaskStates
from bot.task_notify import schedule_new_task_sms, send_new_task_pv
from services.auth import can_create_tasks
from services.sheets import Personnel
from services.sheets_async import SheetsAsync, authorize
from services.sheets_models import resolve_shamsi_date_offset, validate_shamsi_date

logger = logging.getLogger(__name__)

router = Router(name="admin_tasks")


def _normalize_search_str(s: str) -> str:
    s = s.strip().lower()
    for c in ("‌", " ", "-", "_"):
        s = s.replace(c, "")
    return s.replace("ي", "ی").replace("ك", "ک")


def find_matching_employee(query: str, employees: list[Personnel]) -> Personnel | None:
    norm_q = _normalize_search_str(query)
    if not norm_q:
        return None
    for emp in employees:
        if _normalize_search_str(emp.name) == norm_q:
            return emp
    for emp in employees:
        norm_e = _normalize_search_str(emp.name)
        if norm_q in norm_e or norm_e in norm_q:
            return emp
    return None


def find_matching_project(query: str, projects: list[str]) -> str | None:
    norm_q = _normalize_search_str(query)
    if not norm_q:
        return None
    for p in projects:
        if _normalize_search_str(p) == norm_q:
            return p
    for p in projects:
        norm_p = _normalize_search_str(p)
        if norm_q in norm_p or norm_p in norm_q:
            return p
    return None


def parse_priority_str(s: str) -> str | None:
    norm = s.strip().lower()
    if norm in {"high", "فوری", "بالا", "زیاد", "قرمز"}:
        return "High"
    if norm in {"medium", "متوسط", "معمولی", "زرد"}:
        return "Medium"
    if norm in {"low", "پایین", "کم", "سبز"}:
        return "Low"
    return None


def parse_due_date_str(s: str) -> str | None:
    norm = s.strip().lower()
    if norm in {"امروز", "today"}:
        return resolve_shamsi_date_offset(0)
    if norm in {"فردا", "tomorrow"}:
        return resolve_shamsi_date_offset(1)
    if norm in {"پس‌فردا", "پس فردا"}:
        return resolve_shamsi_date_offset(2)
    return validate_shamsi_date(s.strip())


def parse_quick_task(
    text: str, employees: list[Personnel], projects: list[str]
) -> dict | None:
    body = text.strip()
    for prefix in ("/quicktask", "/quick_task", "ثبت تسک:", "ثبت تسک :"):
        if body.startswith(prefix):
            body = body[len(prefix):].strip()
            break
    if not body:
        return None

    if "|" in body:
        parts = [p.strip() for p in body.split("|") if p.strip()]
    elif "\n" in body:
        parts = [p.strip() for p in body.split("\n") if p.strip()]
    else:
        parts = [p.strip() for p in body.split(" ") if p.strip()]

    if len(parts) < 3:
        return {"error": "تعداد بخش‌ها کافی نیست. الگو: نام کارمند | پروژه | عنوان تسک [| اولویت] [| ددلاین]"}

    emp = find_matching_employee(parts[0], employees)
    if emp is None:
        return {"error": f"کارمند با نام «{parts[0]}» یافت نشد."}

    proj = find_matching_project(parts[1], projects)
    if proj is None:
        return {"error": f"پروژه «{parts[1]}» یافت نشد."}

    title = parts[2]
    if len(title) < 2:
        return {"error": "عنوان تسک باید حداقل ۲ کاراکتر باشد."}

    priority = "Medium"
    due_date = resolve_shamsi_date_offset(0) or ""

    if len(parts) >= 4:
        p_pri = parse_priority_str(parts[3])
        p_due = parse_due_date_str(parts[3])
        if p_pri:
            priority = p_pri
        elif p_due:
            due_date = p_due

    if len(parts) >= 5:
        p_pri = parse_priority_str(parts[4])
        p_due = parse_due_date_str(parts[4])
        if p_pri:
            priority = p_pri
        elif p_due:
            due_date = p_due

    return {
        "employee": emp,
        "project": proj,
        "title": title,
        "priority": priority,
        "due_date": due_date,
    }

# In-process lock: FSM flags are not enough — two callbacks can both read
# "not submitting" before either writes. One lock per Telegram user.
_submit_locks: dict[int, asyncio.Lock] = {}


def _submit_lock(user_id: int) -> asyncio.Lock:
    lock = _submit_locks.get(user_id)
    if lock is None:
        lock = asyncio.Lock()
        _submit_locks[user_id] = lock
    return lock


def _same_creator(data: dict, user_id: int) -> bool:
    creator_id = data.get("creator_id")
    if creator_id is None:
        return False
    try:
        return int(creator_id) == user_id
    except (TypeError, ValueError):
        return False


async def _flow_owned_by(callback: CallbackQuery, state: FSMContext) -> bool:
    """Cheap owner check from FSM — no Google Sheets round-trip."""
    if callback.from_user is None:
        return False
    data = await state.get_data()
    if not _same_creator(data, callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return False
    return True


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

    person = await _require_task_creator_message(message)
    if person is None:
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
    await state.update_data(creator_id=person.telegram_id, creator_name=person.name)
    await message.answer(
        "👤 مسئول تسک را انتخاب کنید:",
        reply_markup=personnel_inline_keyboard(employees),
    )


@router.callback_query(F.data.startswith("assign:"), CreateTaskStates.choosing_employee)
async def employee_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return

    if not await _flow_owned_by(callback, state):
        return
    await callback.answer()

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
        assignee_mobile=employee.mobile,
        assignee_sms_enabled=employee.sms_enabled,
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


@router.callback_query(F.data.startswith("projectpage:"), CreateTaskStates.choosing_project)
async def project_page(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    if not await _flow_owned_by(callback, state):
        return
    await callback.answer()
    data = await state.get_data()
    projects: list[str] = data.get("project_list", [])
    try:
        page = int(callback.data.split(":", 1)[1])
    except (ValueError, IndexError):
        page = 0
    await safe_edit_text(
        callback.message,
        "📁 <b>پروژه</b> را انتخاب کنید:\n"
        "🌐 = کار چندپروژه‌ای (مثل آپلودها)\n"
        "📁 = پروژه/پیج مشخص",
        parse_mode="HTML",
        reply_markup=projects_inline_keyboard(projects, page=page),
    )


@router.callback_query(F.data.startswith("projectidx:"), CreateTaskStates.choosing_project)
async def project_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    if not await _flow_owned_by(callback, state):
        return
    await callback.answer()

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
        reply_markup=cancel_flow_keyboard("cancel:create_task"),
    )


@router.message(F.text.startswith(("/quicktask", "/quick_task", "ثبت تسک:", "ثبت تسک :")))
async def handle_quick_task(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    await state.clear()

    person = await _require_task_creator_message(message)
    if person is None:
        return

    employees = await run_sheets_step(message, "get_active_employees", SheetsAsync.get_active_employees())
    if employees is None or not employees:
        await message.answer("هیچ کارمند فعالی در تب Personnel یافت نشد.")
        return

    projects = await run_sheets_step(message, "get_projects", SheetsAsync.get_projects())
    if projects is None or not projects:
        await message.answer("لیست پروژه خالی است.")
        return

    result = parse_quick_task(message.text or "", employees, projects)
    if result is None:
        await message.answer(
            "⚡ <b>ثبت سریع تسک</b>\n\n"
            "فرمت دستور:\n"
            "<code>ثبت تسک: نام کارمند | پروژه | عنوان تسک | اولویت | ددلاین</code>\n\n"
            "📌 <i>اولویت و ددلاین اختیاری هستند.</i>\n\n"
            "<b>مثال:</b>\n"
            "<code>ثبت تسک: شیخ | هما | طراحی پست اینستاگرام | فوری | فردا</code>",
            parse_mode="HTML",
        )
        return

    if "error" in result:
        await message.answer(f"⚠️ {result['error']}")
        return

    emp: Personnel = result["employee"]
    await state.update_data(
        creator_id=person.telegram_id,
        creator_name=person.name,
        assignee_id=emp.telegram_id,
        assignee_name=emp.name,
        assignee_mobile=emp.mobile,
        assignee_sms_enabled=emp.sms_enabled,
        project=result["project"],
        title=result["title"],
        priority=result["priority"],
        due_date=result["due_date"],
    )
    await _show_task_confirmation(message, state)


@router.message(CreateTaskStates.entering_title, F.text, ~F.text.in_(REPLY_MENU_TEXTS))
async def receive_title(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if message.from_user is None or not _same_creator(data, message.from_user.id):
        await state.clear()
        return

    title = (message.text or "").strip()
    if len(title) < 2:
        await message.answer("عنوان باید حداقل ۲ کاراکتر باشد:")
        return

    await state.update_data(title=title)
    if data.get("in_confirm") or data.get("due_date"):
        await state.update_data(in_confirm=False)
        await _show_task_confirmation(message, state)
        return

    await state.set_state(CreateTaskStates.choosing_priority)
    await message.answer("⚡ اولویت را انتخاب کنید:", reply_markup=priority_inline_keyboard())


@router.callback_query(F.data.startswith("priority:"), CreateTaskStates.choosing_priority)
async def priority_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    if not await _flow_owned_by(callback, state):
        return
    await callback.answer()

    priority = callback.data.split(":", 1)[1]
    await state.update_data(priority=priority)
    await state.set_state(CreateTaskStates.choosing_due_date)
    await safe_edit_text(
        callback.message,
        f"⚡ اولویت: <b>{esc(priority)}</b>\n\n"
        "📅 ددلاین را از هفته پیش‌رو انتخاب کنید، یا تاریخ را دستی بنویسید:",
        parse_mode="HTML",
        reply_markup=due_date_inline_keyboard(),
    )


async def _show_task_confirmation(target, state: FSMContext) -> None:
    data = await state.get_data()
    assignee_name = data.get("assignee_name", "-")
    project = data.get("project", "-")
    title = data.get("title", "-")
    priority = data.get("priority", "Medium")
    due_date = data.get("due_date", "-")

    text = (
        "📋 <b>پیش‌نمایش و تأیید تسک:</b>\n\n"
        f"👤 <b>مسئول:</b> {esc(assignee_name)}\n"
        f"📁 <b>پروژه:</b> {esc(project)}\n"
        f"📌 <b>عنوان:</b> {esc(title)}\n"
        f"⚡ <b>اولویت:</b> {esc(priority)}\n"
        f"📅 <b>ددلاین:</b> <code>{esc(due_date)}</code>\n\n"
        "آیا این تسک تأیید و ثبت شود؟"
    )
    await state.set_state(CreateTaskStates.confirming)
    if isinstance(target, CallbackQuery):
        if target.message:
            await safe_edit_text(
                target.message,
                text,
                parse_mode="HTML",
                reply_markup=task_confirm_inline_keyboard(),
            )
    else:
        await target.answer(
            text,
            parse_mode="HTML",
            reply_markup=task_confirm_inline_keyboard(),
        )


@router.callback_query(F.data.startswith("duedate:"), CreateTaskStates.choosing_due_date)
async def due_date_selected(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return

    if not await _flow_owned_by(callback, state):
        return

    payload = callback.data.split(":", 1)[1]
    if payload == "manual":
        await callback.answer()
        await state.set_state(CreateTaskStates.entering_due_date_manual)
        await safe_edit_text(
            callback.message,
            "✏️ <b>ورود دستی ددلاین</b>\n\n"
            "تاریخ شمسی را بنویسید، مثلاً:\n"
            "<code>1405/04/09</code>",
            parse_mode="HTML",
            reply_markup=cancel_flow_keyboard("cancel:create_task"),
        )
        return

    try:
        day_offset = int(payload)
    except ValueError:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    due_date = resolve_shamsi_date_offset(day_offset)
    if due_date is None:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    await callback.answer()
    await state.update_data(due_date=due_date)
    await _show_task_confirmation(callback, state)


@router.callback_query(F.data == "skip:due_date", CreateTaskStates.choosing_due_date)
async def skip_due_date(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    if not await _flow_owned_by(callback, state):
        return
    due_date = resolve_shamsi_date_offset(0)
    if due_date is None:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return
    await callback.answer()
    await state.update_data(due_date=due_date)
    await _show_task_confirmation(callback, state)


@router.message(CreateTaskStates.entering_due_date_manual, F.text, ~F.text.in_(REPLY_MENU_TEXTS))
async def receive_due_date_manual(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    if message.from_user is None or not _same_creator(data, message.from_user.id):
        await state.clear()
        return

    if message.text and message.text.strip().startswith("/"):
        await state.clear()
        await message.answer("❌ ثبت تسک لغو شد.")
        return

    due_date = validate_shamsi_date(message.text or "")
    if due_date is None:
        await message.answer(
            "فرمت تاریخ نامعتبر است.\n"
            "مثال: <code>1405/04/09</code>\n\n"
            "دوباره بنویسید یا «❌ انصراف» را بزنید.",
            parse_mode="HTML",
            reply_markup=cancel_flow_keyboard("cancel:create_task"),
        )
        return

    await state.update_data(due_date=due_date)
    await _show_task_confirmation(message, state)


@router.callback_query(F.data == "taskconfirm:yes", CreateTaskStates.confirming)
async def confirm_task_yes(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    if not await _flow_owned_by(callback, state):
        return
    await callback.answer("در حال ثبت تسک…")
    await _finalize_task(callback.message, callback.from_user, state)


@router.callback_query(F.data == "taskconfirm:edittitle", CreateTaskStates.confirming)
async def confirm_task_edit_title(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or callback.from_user is None:
        return
    if not await _flow_owned_by(callback, state):
        return
    await callback.answer()
    await state.set_state(CreateTaskStates.entering_title)
    await state.update_data(in_confirm=True)
    await safe_edit_text(
        callback.message,
        "✏️ لطفاً عنوان جدید تسک را ارسال کنید:",
        reply_markup=cancel_flow_keyboard("cancel:create_task"),
    )


async def _finalize_task(message: Message | None, from_user, state: FSMContext) -> None:
    if message is None or from_user is None:
        return

    lock = _submit_lock(from_user.id)
    if lock.locked():
        return

    async with lock:
        data = await state.get_data()
        if data.get("task_submitted"):
            return

        assignee_id = data.get("assignee_id")
        assignee_name = data.get("assignee_name", "")
        assignee_mobile = data.get("assignee_mobile", "")
        assignee_sms_enabled = bool(data.get("assignee_sms_enabled", False))
        title = data.get("title", "")
        project = data.get("project", "")
        priority = data.get("priority", "Medium")
        due_date = data.get("due_date", "")
        creator_name = data.get("creator_name") or ""
        creator_id = data.get("creator_id")

        if not data:
            return
        if not assignee_id or not title or not project or not assignee_name:
            await safe_answer(message, INCOMPLETE_DATA_TEXT)
            await state.clear()
            return

        if creator_id is not None and int(creator_id) != from_user.id:
            await state.clear()
            return

        await state.update_data(task_submitted=True)

        if not creator_name:
            try:
                auth = await authorize(from_user.id)
            except Exception:
                logger.exception("authorize failed during task finalize")
                await state.update_data(task_submitted=False)
                await safe_answer(message, SHEETS_ERROR_TEXT)
                return
            if not auth.allowed or auth.personnel is None or not can_create_tasks(auth.personnel):
                await state.clear()
                return
            creator_name = auth.personnel.name

        assignee = Personnel(
            telegram_id=int(assignee_id),
            name=assignee_name,
            role="employee",
            active=True,
            mobile=assignee_mobile,
            sms_enabled=assignee_sms_enabled,
        )

        try:
            task = await SheetsAsync.create_task(
                title=title,
                project=project,
                assignee=assignee,
                created_by_name=creator_name,
                priority=priority,
                due_date=due_date,
            )
        except Exception:
            logger.exception("create_task failed")
            await state.update_data(task_submitted=False)
            await safe_answer(
                message,
                "⚠️ ثبت تسک در Google Sheet ناموفق بود. لطفاً چند ثانیه بعد دوباره «➕ ثبت تسک جدید» را بزنید.",
            )
            return

        await state.clear()

        if not await safe_answer(message, "✅ تسک ثبت شد."):
            await safe_answer(message, "✅ تسک ثبت شد.")

        try:
            full = await SheetsAsync.get_personnel_by_telegram_id(int(assignee_id))
        except Exception:
            logger.warning("personnel lookup after create_task failed", exc_info=True)
            full = None
        if full is None:
            try:
                full = await SheetsAsync.find_personnel_by_name_hint(assignee_name)
            except Exception:
                full = None
        target = full or assignee
        if not target.mobile and assignee_mobile:
            target = Personnel(
                telegram_id=target.telegram_id,
                name=target.name,
                role=target.role,
                active=target.active,
                senior_admin=target.senior_admin,
                view_all_tasks=target.view_all_tasks,
                filming_access=target.filming_access,
                content_access=target.content_access,
                mobile=assignee_mobile,
                sms_enabled=target.sms_enabled or assignee_sms_enabled,
                telegram_notify=target.telegram_notify,
            )

        sent = await send_new_task_pv(message.bot, target, task, creator_name)
        if not sent:
            await safe_answer(
                message,
                ASSIGNEE_NOTIFY_FAILED_TEXT.format(name=esc(target.name)),
                parse_mode="HTML",
            )
        schedule_new_task_sms(target, task, creator_name)


@router.callback_query(F.data == "cancel:create_task")
async def cancel_create_task(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await safe_edit_text(callback.message, "❌ ثبت تسک لغو شد.")


@router.callback_query(
    F.data.startswith("assign:")
    | F.data.startswith("projectidx:")
    | F.data.startswith("projectpage:")
    | F.data.startswith("priority:")
    | F.data.startswith("duedate:")
    | F.data.startswith("taskconfirm:")
    | (F.data == "skip:due_date")
)
async def create_task_stale_callback(callback: CallbackQuery, state: FSMContext) -> None:
    """Recover when inline buttons are tapped after FSM state was lost (e.g. bot restart)."""
    if callback.message is None:
        return

    await callback.answer()
    await state.clear()
    await safe_answer(callback.message, FLOW_EXPIRED_TEXT)
