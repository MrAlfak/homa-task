"""Employee task list and status updates."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.formatting import esc
from bot.keyboards import (
    ADMIN_MY_TASKS_TEXTS,
    DONE_TASKS_TEXTS,
    MY_TASKS_TEXTS,
    STATUS_LABELS,
    TEAM_TASKS_TEXTS,
    task_detail_keyboard,
    task_list_keyboard,
    team_users_keyboard,
    user_tasks_keyboard,
)
from services.auth import can_view_all_tasks
from services.sheets import Personnel, Task
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="employee_tasks")


def format_task_detail(task: Task, *, show_assignee: bool = False) -> str:
    due = f"\n📅 ددلاین: {esc(task.due_date)}" if task.due_date else ""
    assignee = (
        f"\n👤 مسئول: {esc(task.assignee_name)}"
        if show_assignee and task.assignee_name
        else ""
    )
    return (
        f"📌 <b>{esc(task.title)}</b>\n"
        f"📁 {esc(task.project)}\n"
        f"📊 {esc(STATUS_LABELS.get(task.status, task.status))}\n"
        f"⚡ {esc(task.priority)}\n"
        f"🕐 {esc(task.created_at)}\n"
        f"👤 ایجادکننده: {esc(task.created_by)}{assignee}{due}"
    )


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

    await message.answer("⏳ در حال بارگذاری…")

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


async def send_task_list(
    message: Message,
    telegram_id: int,
    *,
    status: str | None,
    scope: str = "own",
) -> None:
    await message.answer("⏳ در حال بارگذاری تسک‌ها…")

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

    await message.answer(
        f"{title} ({len(tasks)} مورد):\n\nیک تسک را انتخاب کنید:",
        reply_markup=task_list_keyboard(tasks),
    )


@router.message(F.text.in_(TEAM_TASKS_TEXTS))
async def list_all_tasks(message: Message) -> None:
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
    await callback.message.edit_text(
        f"📌 تسک‌های <b>{esc(employee.name)}</b> ({len(tasks)} مورد):\n\nیک تسک را انتخاب کنید:",
        reply_markup=user_tasks_keyboard(tasks),
        parse_mode="HTML",
    )


@router.message(F.text.in_(MY_TASKS_TEXTS))
async def list_my_tasks(message: Message) -> None:
    if message.from_user is None:
        return
    await send_task_list(message, message.from_user.id, status=None, scope="own")


@router.message(F.text.in_(DONE_TASKS_TEXTS))
async def list_done_tasks(message: Message) -> None:
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
    can_update = task.assignee_name == auth.personnel.name
    back_callback = await _back_callback_for_task(auth.personnel, task)
    await callback.message.edit_text(
        format_task_detail(task, show_assignee=show_assignee),
        reply_markup=task_detail_keyboard(
            task,
            can_update_status=can_update,
            back_callback=back_callback,
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

    show_assignee = can_view_all_tasks(auth.personnel)
    can_update = task.assignee_name == auth.personnel.name
    back_callback = await _back_callback_for_task(auth.personnel, task)
    await callback.message.edit_text(
        format_task_detail(task, show_assignee=show_assignee),
        reply_markup=task_detail_keyboard(
            task,
            can_update_status=can_update,
            back_callback=back_callback,
        ),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "noop")
async def noop_callback(callback: CallbackQuery) -> None:
    await callback.answer()
