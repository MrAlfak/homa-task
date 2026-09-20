"""Employee task list and status updates."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.formatting import esc
from bot.keyboards import (
    DONE_TASKS_TEXTS,
    MY_TASKS_ALL_TEXTS,
    REPLY_MENU_TEXTS,
    STATUS_LABELS,
    TEAM_TASKS_TEXTS,
    cancel_flow_keyboard,
    edit_due_date_inline_keyboard,
    edit_priority_inline_keyboard,
    task_detail_keyboard,
    task_list_keyboard,
    team_users_keyboard,
    user_tasks_keyboard,
)
from bot.states import TaskEditStates, TaskNoteStates
from services.auth import can_view_all_tasks, is_admin, is_senior_admin
from services.sheets import Personnel, Task
from services.sheets_async import SheetsAsync, authorize
from services.sheets_models import (
    parse_due_as_jalali,
    resolve_shamsi_date_offset,
    tehran_today,
    validate_shamsi_date,
)

logger = logging.getLogger(__name__)

router = Router(name="employee_tasks")


def format_task_detail(task: Task, *, show_assignee: bool = False) -> str:
    due = f"\n📅 ددلاین: {esc(task.due_date)}" if task.due_date else ""
    assignee = (
        f"\n👤 مسئول: {esc(task.assignee_name)}"
        if show_assignee and task.assignee_name
        else ""
    )
    desc = f"\n📝 توضیحات: {esc(task.description)}" if task.description else ""
    return (
        f"📌 <b>{esc(task.title)}</b>\n"
        f"📁 {esc(task.project)}\n"
        f"📊 {esc(STATUS_LABELS.get(task.status, task.status))}\n"
        f"⚡ {esc(task.priority)}\n"
        f"🕐 {esc(task.created_at)}\n"
        f"👤 ایجادکننده: {esc(task.created_by)}{assignee}{due}{desc}"
    )


async def _notify_creator_task_done(bot, task: Task, employee_name: str) -> None:
    if not task.created_by:
        return
    try:
        personnel_list = await SheetsAsync.get_active_personnel()
        creator = next((p for p in personnel_list if p.name == task.created_by), None)
        if creator and creator.telegram_id and creator.telegram_id > 0:
            msg = (
                f"🎉 <b>تسک انجام شد!</b>\n\n"
                f"📌 <b>{esc(task.title)}</b>\n"
                f"📁 پروژه: {esc(task.project)}\n"
                f"👤 انجام‌شده توسط: <b>{esc(employee_name)}</b>"
            )
            await bot.send_message(creator.telegram_id, msg, parse_mode="HTML")
    except Exception:
        logger.exception("Failed to notify creator about completed task %s", task.id)


async def _require_team_viewer(telegram_id: int):
    auth = await authorize(telegram_id)
    if not auth.allowed or auth.personnel is None:
        return None, auth
    if not can_view_all_tasks(auth.personnel):
        return None, auth
    return auth.personnel, auth


async def _telegram_id_for_name(name: str) -> int | None:
    for person in await SheetsAsync.get_active_personnel():
        if person.name == name:
            return person.telegram_id
    return None


async def _back_callback_for_task(viewer: Personnel, task: Task) -> str:
    if can_view_all_tasks(viewer) and task.assignee_name != viewer.name:
        assignee_tid = await _telegram_id_for_name(task.assignee_name)
        if assignee_tid is not None:
            return f"task:user:{assignee_tid}"
    return "task:list"


async def _show_team_user_picker(message: Message, *, edit: bool = False) -> None:
    if message.from_user is None:
        return

    if message.bot and message.chat:
        try:
            await message.bot.send_chat_action(message.chat.id, "typing")
        except Exception:
            pass

    viewer, auth = await _require_team_viewer(message.from_user.id)
    if viewer is None:
        text = (
            "دسترسی مشاهده تسک‌های دیگران برای شما فعال نیست.\n"
            "در Personnel هر دو ستون «مدیر ارشد» و «مشاهده همه تسک» باید TRUE باشند."
        )
        if auth.allowed:
            await message.answer(text)
        else:
            await message.answer(auth.reason, parse_mode="HTML")
        return

    employees = await SheetsAsync.get_active_employees()
    text = "👥 <b>تسک‌های گروه</b>\n\nیک نفر را انتخاب کنید:"
    markup = team_users_keyboard(employees)

    if edit and hasattr(message, "edit_text"):
        await message.edit_text(text, reply_markup=markup, parse_mode="HTML")
    else:
        await message.answer(text, reply_markup=markup, parse_mode="HTML")


def _format_task_overview(title: str, tasks: list[Task]) -> tuple[str, list[Task]]:
    """Format categorized message (today, overdue, other) and return priority-sorted tasks."""
    today = tehran_today()
    overdue_tasks: list[Task] = []
    today_tasks: list[Task] = []
    other_tasks: list[Task] = []

    for t in tasks:
        if t.status in ("done", "cancelled"):
            continue
        due = parse_due_as_jalali(t.due_date)
        if due is not None and due < today:
            overdue_tasks.append(t)
        elif due is not None and due == today:
            today_tasks.append(t)
        else:
            other_tasks.append(t)

    sorted_tasks = overdue_tasks + today_tasks + other_tasks
    if not sorted_tasks:
        sorted_tasks = tasks

    lines: list[str] = [f"<b>{title}</b> ({len(tasks)} مورد)\n"]

    if today_tasks:
        lines.append("📅 <b>تسک‌های امروز:</b>")
        for t in today_tasks:
            lines.append(f"  ▫️ {esc(t.title)} (📁 {esc(t.project)})")
        lines.append("")

    if overdue_tasks:
        lines.append("🔴 <b>تسک‌های معوقه:</b>")
        for t in overdue_tasks:
            due_str = f" | ⏱ ددلاین: {esc(t.due_date)}" if t.due_date else ""
            lines.append(f"  ▫️ {esc(t.title)} (📁 {esc(t.project)}{due_str})")
        lines.append("")

    if other_tasks:
        lines.append(f"⏳ <b>سایر تسک‌ها ({len(other_tasks)} مورد):</b>")
        for t in other_tasks[:6]:
            due_str = f" | ⏱ ددلاین: {esc(t.due_date)}" if t.due_date else ""
            lines.append(f"  ▫️ {esc(t.title)} (📁 {esc(t.project)}{due_str})")
        if len(other_tasks) > 6:
            lines.append(f"  ... و {len(other_tasks) - 6} تسک دیگر")
        lines.append("")

    lines.append("👇 برای مشاهده جزئیات یا تغییر وضعیت، تسک را انتخاب کنید:")
    return "\n".join(lines), sorted_tasks


async def send_task_list(
    message: Message,
    telegram_id: int,
    *,
    status: str | None,
    scope: str = "own",
) -> None:
    if message.bot and message.chat:
        try:
            await message.bot.send_chat_action(message.chat.id, "typing")
        except Exception:
            pass

    auth = await authorize(telegram_id)
    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return

    tasks = await SheetsAsync.get_tasks_for_assignee(auth.personnel, status=status)

    if status == "done":
        title = "✅ تسک‌های انجام‌شده"
    elif status == "pending":
        title = "⏳ تسک‌های در انتظار"
    else:
        title = "📌 تسک‌های من"

    if not tasks:
        await message.answer(f"{title}\n\nتسکی یافت نشد.")
        return

    text, sorted_tasks = _format_task_overview(title, tasks)
    await message.answer(
        text,
        reply_markup=task_list_keyboard(sorted_tasks),
        parse_mode="HTML",
    )


@router.message(F.text.in_(TEAM_TASKS_TEXTS))
async def list_all_tasks(message: Message, state: FSMContext) -> None:
    await state.clear()
    await _show_team_user_picker(message)


@router.callback_query(F.data == "task:users")
async def callback_team_users(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    viewer, auth = await _require_team_viewer(callback.from_user.id)
    if viewer is None:
        await callback.message.answer("دسترسی ندارید.")
        return

    employees = await SheetsAsync.get_active_employees()
    await callback.message.edit_text(
        "👥 <b>تسک‌های گروه</b>\n\nیک نفر را انتخاب کنید:",
        reply_markup=team_users_keyboard(employees),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:user:"))
async def list_user_tasks(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    await callback.answer()

    viewer, auth = await _require_team_viewer(callback.from_user.id)
    if viewer is None:
        await callback.message.answer("دسترسی ندارید.")
        return

    try:
        member_tid = int(callback.data.removeprefix("task:user:"))
    except ValueError:
        await callback.message.answer("کاربر نامعتبر.")
        return

    employee = await SheetsAsync.get_personnel_by_telegram_id(member_tid)
    if employee is None:
        await callback.message.answer("کارمند یافت نشد.")
        return

    tasks = await SheetsAsync.get_tasks_for_assignee(employee, status=None)
    text, sorted_tasks = _format_task_overview(f"📌 تسک‌های <b>{esc(employee.name)}</b>", tasks)
    await callback.message.edit_text(
        text,
        reply_markup=user_tasks_keyboard(sorted_tasks, member_tid=member_tid),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:up:"))
async def list_user_tasks_page(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return
    await callback.answer()
    viewer, _auth = await _require_team_viewer(callback.from_user.id)
    if viewer is None:
        await callback.message.answer("دسترسی ندارید.")
        return
    try:
        rest = callback.data.removeprefix("task:up:")
        member_str, page_str = rest.rsplit(":", 1)
        member_tid = int(member_str)
        page = int(page_str)
    except ValueError:
        await callback.message.answer("صفحه نامعتبر.")
        return
    employee = await SheetsAsync.get_personnel_by_telegram_id(member_tid)
    if employee is None:
        await callback.message.answer("کارمند یافت نشد.")
        return
    tasks = await SheetsAsync.get_tasks_for_assignee(employee, status=None)
    await callback.message.edit_text(
        f"📌 تسک‌های <b>{esc(employee.name)}</b> ({len(tasks)} مورد):\n\nیک تسک را انتخاب کنید:",
        reply_markup=user_tasks_keyboard(tasks, member_tid=member_tid, page=page),
        parse_mode="HTML",
    )


@router.message(F.text.in_(MY_TASKS_ALL_TEXTS))
async def list_my_tasks(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    await send_task_list(message, message.from_user.id, status=None, scope="own")


@router.message(F.text.in_(DONE_TASKS_TEXTS))
async def list_done_tasks(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return
    await send_task_list(message, message.from_user.id, status="done", scope="own")


@router.callback_query(F.data == "task:list")
async def callback_task_list(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    await callback.answer()
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.message.answer("دسترسی ندارید.")
        return

    tasks = await SheetsAsync.get_tasks_for_assignee(auth.personnel)
    await callback.message.edit_text(
        f"📌 تسک‌های شما ({len(tasks)} مورد):",
        reply_markup=task_list_keyboard(tasks),
    )


@router.callback_query(F.data.startswith("task:page:"))
async def callback_task_list_page(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    await callback.answer()
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.message.answer("دسترسی ندارید.")
        return
    try:
        page = int(callback.data.removeprefix("task:page:"))
    except ValueError:
        page = 0
    tasks = await SheetsAsync.get_tasks_for_assignee(auth.personnel)
    await callback.message.edit_text(
        f"📌 تسک‌های شما ({len(tasks)} مورد):",
        reply_markup=task_list_keyboard(tasks, page=page),
    )


@router.callback_query(F.data.startswith("task:quickdone:"))
async def quick_done_task(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    task_id = callback.data.removeprefix("task:quickdone:")
    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task is None:
        await callback.answer("تسک یافت نشد.", show_alert=True)
        return

    updated = await SheetsAsync.update_task_status(task_id, auth.personnel, "done")
    if not updated:
        await callback.answer("⚠️ به‌روزرسانی وضعیت ناموفق بود.", show_alert=True)
        return

    await callback.answer("✅ تسک انجام شد!", show_alert=False)
    await _notify_creator_task_done(callback.bot, task, auth.personnel.name)

    tasks = await SheetsAsync.get_tasks_for_assignee(auth.personnel)
    await callback.message.edit_text(
        f"📌 تسک‌های شما ({len(tasks)} مورد):",
        reply_markup=task_list_keyboard(tasks),
    )


@router.callback_query(F.data.startswith("taskfilter:"))
async def callback_task_filter(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    filter_mode = callback.data.removeprefix("taskfilter:")
    await callback.answer()

    tasks = await SheetsAsync.get_tasks_for_assignee(auth.personnel)
    today_str = resolve_shamsi_date_offset(0) or ""

    if filter_mode == "high":
        filtered = [t for t in tasks if (t.priority or "").lower() == "high"]
    elif filter_mode == "today":
        filtered = [t for t in tasks if t.due_date and t.due_date.strip() == today_str]
    else:
        filter_mode = "all"
        filtered = tasks

    label_map = {"all": "همه", "high": "⚡ فوری", "today": "📅 امروز"}
    await callback.message.edit_text(
        f"📌 تسک‌های شما [{label_map.get(filter_mode, 'همه')}] ({len(filtered)} مورد):",
        reply_markup=task_list_keyboard(filtered, active_filter=filter_mode),
    )


@router.callback_query(F.data.startswith("task:view:"))
async def view_task(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    await callback.answer()
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.message.answer("دسترسی ندارید.")
        return

    task_id = callback.data.removeprefix("task:view:")
    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task is None:
        await callback.message.answer("تسک یافت نشد.")
        return

    show_assignee = can_view_all_tasks(auth.personnel)
    is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
    can_update = (
        task.assignee_name == auth.personnel.name
        or is_mgr
    )
    back_callback = await _back_callback_for_task(auth.personnel, task)
    await callback.message.edit_text(
        format_task_detail(task, show_assignee=show_assignee),
        reply_markup=task_detail_keyboard(
            task,
            can_update_status=can_update,
            back_callback=back_callback,
            is_manager=is_mgr,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:status:"))
async def update_task_status(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    payload = callback.data.removeprefix("task:status:")
    task_id, new_status = payload.rsplit(":", 1)

    if new_status not in {"in_progress", "done", "cancelled"}:
        await callback.answer("وضعیت نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال به‌روزرسانی…")

    updated = await SheetsAsync.update_task_status(task_id, auth.personnel, new_status)
    if not updated:
        await callback.message.answer("⚠️ به‌روزرسانی وضعیت ناموفق بود.")
        return

    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task is None:
        await callback.message.answer("⚠️ تسک یافت نشد.")
        return

    if new_status == "done":
        await _notify_creator_task_done(callback.bot, task, auth.personnel.name)

    show_assignee = can_view_all_tasks(auth.personnel)
    is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
    can_update = (
        task.assignee_name == auth.personnel.name
        or is_mgr
    )
    back_callback = await _back_callback_for_task(auth.personnel, task)
    await callback.message.edit_text(
        format_task_detail(task, show_assignee=show_assignee),
        reply_markup=task_detail_keyboard(
            task,
            can_update_status=can_update,
            back_callback=back_callback,
            is_manager=is_mgr,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:note:"))
async def prompt_task_note(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    task_id = callback.data.removeprefix("task:note:")
    await callback.answer()
    await state.set_state(TaskNoteStates.entering_note)
    await state.update_data(task_id=task_id)
    await callback.message.answer(
        "💬 <b>ثبت / ویرایش یادداشت</b>\n\n"
        "لطفاً توضیحات، لینک یا گزارش پیشرفت خود را برای این تسک ارسال کنید:\n"
        "(برای انصراف «❌ انصراف» را بزنید)",
        parse_mode="HTML",
        reply_markup=cancel_flow_keyboard("cancel:task_note"),
    )


@router.callback_query(F.data == "cancel:task_note", TaskNoteStates.entering_note)
async def cancel_task_note(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text("❌ ثبت یادداشت لغو شد.")


@router.message(TaskNoteStates.entering_note, F.text, ~F.text.in_(REPLY_MENU_TEXTS))
async def receive_task_note(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        await state.clear()
        return

    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return

    text = (message.text or "").strip()
    if text.startswith("/") or text in ("❌ انصراف", "انصراف"):
        await state.clear()
        await message.answer("❌ ثبت یادداشت لغو شد.")
        return

    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await state.clear()
        await message.answer(auth.reason, parse_mode="HTML")
        return

    await state.clear()
    success = await SheetsAsync.update_task_note(task_id, auth.personnel, text)
    if success:
        await message.answer("✅ یادداشت تسک با موفقیت ثبت شد.")
    else:
        await message.answer("⚠️ خطا در ثبت یادداشت تسک.")

    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task:
        show_assignee = can_view_all_tasks(auth.personnel)
        is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
        can_update = task.assignee_name == auth.personnel.name or is_mgr
        back_callback = await _back_callback_for_task(auth.personnel, task)
        await message.answer(
            format_task_detail(task, show_assignee=show_assignee),
            reply_markup=task_detail_keyboard(
                task,
                can_update_status=can_update,
                back_callback=back_callback,
                is_manager=is_mgr,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("task:editdue:"))
async def edit_task_due_date(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    if not (is_admin(auth.personnel) or is_senior_admin(auth.personnel)):
        await callback.answer("فقط مدیران امکان تغییر ددلاین دارند.", show_alert=True)
        return

    task_id = callback.data.removeprefix("task:editdue:")
    await callback.answer()
    await callback.message.edit_text(
        "📅 <b>تغییر ددلاین تسک</b>\n\nتاریخ جدید را انتخاب کنید یا به صورت دستی بنویسید:",
        reply_markup=edit_due_date_inline_keyboard(task_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:setdue:"))
async def set_task_due_date(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    if not (is_admin(auth.personnel) or is_senior_admin(auth.personnel)):
        await callback.answer("فقط مدیران امکان تغییر ددلاین دارند.", show_alert=True)
        return

    payload = callback.data.removeprefix("task:setdue:")
    task_id, val = payload.split(":", 1)

    if val == "manual":
        await callback.answer()
        await state.set_state(TaskEditStates.entering_due_date_manual)
        await state.update_data(task_id=task_id)
        await callback.message.answer(
            "✏️ <b>ورود دستی ددلاین جدید</b>\n\n"
            "تاریخ شمسی را بنویسید، مثلاً:\n"
            "<code>1405/04/09</code>",
            parse_mode="HTML",
            reply_markup=cancel_flow_keyboard("cancel:task_edit"),
        )
        return

    try:
        offset = int(val)
    except ValueError:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    due_date = resolve_shamsi_date_offset(offset)
    if not due_date:
        await callback.answer("تاریخ نامعتبر.", show_alert=True)
        return

    await callback.answer("در حال تغییر ددلاین…")
    success = await SheetsAsync.update_task_due_date(task_id, auth.personnel, due_date)
    if not success:
        await callback.answer("⚠️ خطا در تغییر ددلاین.", show_alert=True)
        return

    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task:
        show_assignee = can_view_all_tasks(auth.personnel)
        is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
        can_update = task.assignee_name == auth.personnel.name or is_mgr
        back_callback = await _back_callback_for_task(auth.personnel, task)
        await callback.message.edit_text(
            format_task_detail(task, show_assignee=show_assignee),
            reply_markup=task_detail_keyboard(
                task,
                can_update_status=can_update,
                back_callback=back_callback,
                is_manager=is_mgr,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "cancel:task_edit")
async def cancel_task_edit(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.edit_text("❌ ویرایش تسک لغو شد.")


@router.message(TaskEditStates.entering_due_date_manual, F.text, ~F.text.in_(REPLY_MENU_TEXTS))
async def receive_edit_due_date_manual(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        await state.clear()
        return
    data = await state.get_data()
    task_id = data.get("task_id")
    if not task_id:
        await state.clear()
        return

    text = (message.text or "").strip()
    if text.startswith("/") or text in ("❌ انصراف", "انصراف"):
        await state.clear()
        await message.answer("❌ ویرایش ددلاین لغو شد.")
        return

    due_date = validate_shamsi_date(text)
    if due_date is None:
        await message.answer(
            "فرمت تاریخ نامعتبر است.\n"
            "مثال: <code>1405/04/09</code>\n\n"
            "دوباره بنویسید یا «❌ انصراف» را بزنید.",
            parse_mode="HTML",
            reply_markup=cancel_flow_keyboard("cancel:task_edit"),
        )
        return

    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await state.clear()
        return

    await state.clear()
    success = await SheetsAsync.update_task_due_date(task_id, auth.personnel, due_date)
    if success:
        await message.answer("✅ ددلاین با موفقیت به‌روزرسانی شد.")
    else:
        await message.answer("⚠️ خطا در به‌روزرسانی ددلاین.")

    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task:
        show_assignee = can_view_all_tasks(auth.personnel)
        is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
        can_update = task.assignee_name == auth.personnel.name or is_mgr
        back_callback = await _back_callback_for_task(auth.personnel, task)
        await message.answer(
            format_task_detail(task, show_assignee=show_assignee),
            reply_markup=task_detail_keyboard(
                task,
                can_update_status=can_update,
                back_callback=back_callback,
                is_manager=is_mgr,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data.startswith("task:editpri:"))
async def edit_task_priority(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    if not (is_admin(auth.personnel) or is_senior_admin(auth.personnel)):
        await callback.answer("فقط مدیران امکان تغییر اولویت دارند.", show_alert=True)
        return

    task_id = callback.data.removeprefix("task:editpri:")
    await callback.answer()
    await callback.message.edit_text(
        "⚡ <b>تغییر اولویت تسک</b>\n\nاولویت جدید را انتخاب کنید:",
        reply_markup=edit_priority_inline_keyboard(task_id),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("task:setpri:"))
async def set_task_priority(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    auth = await authorize(callback.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    if not (is_admin(auth.personnel) or is_senior_admin(auth.personnel)):
        await callback.answer("فقط مدیران امکان تغییر اولویت دارند.", show_alert=True)
        return

    payload = callback.data.removeprefix("task:setpri:")
    task_id, priority = payload.split(":", 1)

    await callback.answer("در حال تغییر اولویت…")
    success = await SheetsAsync.update_task_priority(task_id, auth.personnel, priority)
    if not success:
        await callback.answer("⚠️ خطا در تغییر اولویت.", show_alert=True)
        return

    task = await SheetsAsync.get_task_by_id(task_id, auth.personnel)
    if task:
        show_assignee = can_view_all_tasks(auth.personnel)
        is_mgr = is_admin(auth.personnel) or is_senior_admin(auth.personnel)
        can_update = task.assignee_name == auth.personnel.name or is_mgr
        back_callback = await _back_callback_for_task(auth.personnel, task)
        await callback.message.edit_text(
            format_task_detail(task, show_assignee=show_assignee),
            reply_markup=task_detail_keyboard(
                task,
                can_update_status=can_update,
                back_callback=back_callback,
                is_manager=is_mgr,
            ),
            parse_mode="HTML",
        )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()
