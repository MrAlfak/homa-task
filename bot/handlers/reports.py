"""Manager chart reports sent as Telegram photos."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import BufferedInputFile, CallbackQuery, Message

from bot.keyboards import REPORTS_TEXTS, reports_inline_keyboard
from services.auth import can_access_report_kind, can_access_reports, enabled_report_kinds
from services.sheets_async import SheetsAsync, authorize
from services.sheets_models import REPORT_KIND_LABELS

logger = logging.getLogger(__name__)

router = Router(name="reports")

NO_ACCESS = (
    "دسترسی گزارش مدیر برای شما فعال نیست.\n"
    "در Personnel ستون «گزارش مدیر» باید TRUE باشد."
)
KIND_CAPTION = dict(REPORT_KIND_LABELS)


async def _require_reports(message_or_user_id) -> object | None:
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
        logger.exception("authorize failed for reports telegram_id=%s", telegram_id)
        if reply is not None:
            await reply.answer("⚠️ اتصال به Google Sheet برقرار نشد.")
        return None
    if not auth.allowed or auth.personnel is None:
        if reply is not None:
            await reply.answer(auth.reason, parse_mode="HTML")
        return None
    if not can_access_reports(auth.personnel):
        if reply is not None:
            await reply.answer(NO_ACCESS)
        return None
    return auth.personnel


@router.message(F.text.in_(REPORTS_TEXTS))
async def reports_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    person = await _require_reports(message)
    if person is None:
        return
    kinds = enabled_report_kinds(person)
    await message.answer(
        "📊 <b>گزارش‌های مدیریتی</b>\n\nیک نمودار را انتخاب کنید. عکس در همین پی‌وی می‌آید.",
        parse_mode="HTML",
        reply_markup=reports_inline_keyboard(kinds),
    )


@router.callback_query(F.data == "report:menu")
async def reports_menu_callback(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    person = await _require_reports(callback.from_user.id)
    if person is None:
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return
    await callback.answer()
    kinds = enabled_report_kinds(person)
    await callback.message.answer(
        "📊 <b>گزارش‌های مدیریتی</b>\n\nیک نمودار را انتخاب کنید.",
        parse_mode="HTML",
        reply_markup=reports_inline_keyboard(kinds),
    )


@router.callback_query(F.data.startswith("report:"))
async def send_report(callback: CallbackQuery) -> None:
    if callback.from_user is None or callback.message is None:
        return
    kind = callback.data.removeprefix("report:")
    if kind == "menu":
        return
    person = await _require_reports(callback.from_user.id)
    if person is None or not can_access_report_kind(person, kind):
        await callback.answer("دسترسی این گزارش را ندارید.", show_alert=True)
        return
    await callback.answer("در حال ساخت نمودار…")
    try:
        tasks = await SheetsAsync.list_main_tasks()
        from services.charts import render_report

        png = render_report(kind, tasks, kinds=enabled_report_kinds(person))
    except Exception:
        logger.exception("report render failed kind=%s", kind)
        await callback.message.answer("⚠️ ساخت نمودار ناموفق بود. چند ثانیه بعد دوباره تلاش کنید.")
        return
    caption = f"📊 {KIND_CAPTION.get(kind, kind)}"
    await callback.message.answer_photo(
        BufferedInputFile(png, filename=f"report-{kind}.png"),
        caption=caption,
    )
