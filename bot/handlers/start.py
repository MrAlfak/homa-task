"""Start command and main menu routing."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from bot.formatting import esc
from bot.keyboards import (
    ADMIN_MY_TASKS_TEXTS,
    CONTENT_BUTTON,
    FILMING_BUTTON,
    OPEN_SHEET_TEXTS,
    TEAM_TASKS_BUTTON,
    main_menu_keyboard,
    open_sheet_inline_keyboard,
)
from services.auth import (
    can_access_content,
    can_access_filming,
    can_create_tasks,
    can_view_all_tasks,
    is_admin,
    is_senior_admin,
)
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="start")


def _welcome_text(personnel) -> str:
    if is_senior_admin(personnel):
        role_line = "شما به عنوان <b>مدیر ارشد</b> وارد شدید."
    elif is_admin(personnel):
        role_line = "شما به عنوان <b>مدیر</b> وارد شدید."
    else:
        role_line = "به ربات مدیریت تسک خوش آمدید."

    hints: list[str] = []
    if can_create_tasks(personnel):
        hints.append("می‌توانید با «➕ ثبت تسک جدید» برای پرسنل تسک ثبت کنید.")
    if can_access_filming(personnel):
        hints.append(f"با «{esc(FILMING_BUTTON)}» برنامه تصویر برداری ثبت یا مشاهده کنید.")
    if can_access_content(personnel):
        hints.append(f"با «{esc(CONTENT_BUTTON)}» تولید محتوا (پست/استوری) ثبت یا مشاهده کنید.")
    if can_view_all_tasks(personnel):
        hints.append(f"با «{esc(TEAM_TASKS_BUTTON)}» عضو گروه را انتخاب کنید و تسک‌هایش را ببینید.")
    elif is_senior_admin(personnel):
        hints.append("برای «تسک‌های گروه»، ستون «مشاهده همه تسک» را هم TRUE کنید.")
    elif not is_admin(personnel):
        hints.append("از منوی زیر تسک‌های خود را مشاهده کنید.")

    hint_block = "\n".join(hints)
    return f"سلام {esc(personnel.name)}! 👋\n{role_line}\n\n{hint_block}"


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return

    await message.answer("⏳ در حال بارگذاری…")

    try:
        auth = await authorize(message.from_user.id)
    except Exception:
        logger.exception("authorize failed on /start for %s", message.from_user.id)
        await message.answer(
            "⚠️ اتصال به Google Sheet برقرار نشد. چند ثانیه بعد دوباره <b>/start</b> بزنید.",
            parse_mode="HTML",
        )
        return

    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return

    personnel = auth.personnel
    await message.answer(
        _welcome_text(personnel),
        reply_markup=main_menu_keyboard(personnel),
        parse_mode="HTML",
    )


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    if message.from_user is None:
        return
    await message.answer(
        f"شناسه تلگرام شما:\n<code>{message.from_user.id}</code>",
        parse_mode="HTML",
    )


@router.message(F.text.in_(OPEN_SHEET_TEXTS))
async def open_sheet(message: Message) -> None:
    if message.from_user is None:
        return

    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return

    sheet_url = await SheetsAsync.get_sheet_url(auth.personnel)
    if is_admin(auth.personnel) or can_view_all_tasks(auth.personnel):
        hint = "تب Tasks برای مشاهده همه تسک‌ها باز می‌شود."
    else:
        hint = f"تب شخصی <b>{esc(auth.personnel.name)}</b> باز می‌شود."

    await message.answer(
        f"📊 {hint}\n\nروی دکمه زیر بزنید:",
        reply_markup=open_sheet_inline_keyboard(sheet_url),
        parse_mode="HTML",
    )


@router.message(F.text.in_(ADMIN_MY_TASKS_TEXTS))
async def admin_my_tasks_shortcut(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return
    if not is_admin(auth.personnel) and not is_senior_admin(auth.personnel):
        return

    from bot.handlers.employee_tasks import send_task_list

    await send_task_list(message, message.from_user.id, status=None, scope="own")


try:
    from bot.handlers.announce import router as announce_router

    router.include_router(announce_router)
    logger.info("Announce routes mounted on start.router")
except ImportError:
    logger.warning("Announce module not found; /announce unavailable")
