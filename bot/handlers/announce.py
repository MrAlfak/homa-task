"""Senior admin: broadcast changelog to all registered bot users (private DM)."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message

from bot.keyboards import (
    CANCEL_ANNOUNCE_BUTTON,
    CONFIRM_ANNOUNCE_BUTTON,
    announce_confirm_inline_keyboard,
    announce_confirm_reply_keyboard,
    main_menu_keyboard,
)
from bot.messages.changelog import build_changelog_announcement
from services.auth import is_senior_admin
from services.sheets import Personnel
from services.sheets_async import SheetsAsync, authorize

logger = logging.getLogger(__name__)

router = Router(name="announce")

_broadcast_in_progress: set[int] = set()


@dataclass(frozen=True)
class BroadcastResult:
    total: int
    sent: int
    failed: int
    failures: tuple[str, ...]


async def _is_senior_admin_user(telegram_id: int) -> bool:
    try:
        auth = await authorize(telegram_id)
    except Exception:
        logger.exception("authorize failed for telegram_id=%s", telegram_id)
        return False
    return auth.allowed and auth.personnel is not None and is_senior_admin(auth.personnel)


def _menu(personnel: Personnel | None):
    return main_menu_keyboard(personnel) if personnel else None


async def _broadcast_to_all_users(bot: Bot) -> BroadcastResult:
    me = await bot.get_me()
    body = build_changelog_announcement(bot_name=me.full_name)
    recipients = await SheetsAsync.get_broadcast_recipients()
    sent = 0
    failures: list[str] = []

    for person in recipients:
        try:
            await bot.send_message(person.telegram_id, body, parse_mode="HTML")
            sent += 1
            await asyncio.sleep(0.06)
        except Exception as exc:
            failures.append(f"{person.name} ({person.telegram_id}): {type(exc).__name__}")
            logger.warning(
                "Announce DM failed for %s (%s): %s",
                person.name,
                person.telegram_id,
                exc,
            )

    return BroadcastResult(
        total=len(recipients),
        sent=sent,
        failed=len(failures),
        failures=tuple(failures[:10]),
    )


def _format_result(result: BroadcastResult) -> str:
    lines = [
        "✅ <b>اعلان بروزرسانی ارسال شد.</b>",
        "",
        f"👥 کل گیرندگان: <code>{result.total}</code>",
        f"📨 ارسال موفق: <code>{result.sent}</code>",
        f"❌ ناموفق: <code>{result.failed}</code>",
    ]
    if result.failures:
        lines.append("")
        lines.append("<b>نمونه خطاها:</b>")
        for item in result.failures:
            lines.append(f"• <code>{item}</code>")
        if result.failed > len(result.failures):
            lines.append(f"• … و {result.failed - len(result.failures)} مورد دیگر")
    return "\n".join(lines)


async def _execute_broadcast(reply: Message, bot: Bot) -> None:
    if reply.from_user is None:
        return

    user_id = reply.from_user.id
    if user_id in _broadcast_in_progress:
        await reply.answer("⏳ ارسال قبلی هنوز در جریان است.", parse_mode="HTML")
        return

    _broadcast_in_progress.add(user_id)
    try:
        auth = await authorize(user_id)
        personnel = auth.personnel
        recipients = await SheetsAsync.get_broadcast_recipients()

        if not recipients:
            await reply.answer(
                "⚠️ هیچ کاربری با شناسه تلگرام در Personnel یافت نشد.",
                reply_markup=_menu(personnel),
            )
            return

        logger.info(
            "Broadcast started by %s to %d recipients",
            user_id,
            len(recipients),
        )
        await reply.answer(
            f"⏳ در حال ارسال به <b>{len(recipients)}</b> نفر…",
            parse_mode="HTML",
        )

        result = await _broadcast_to_all_users(bot)
        logger.info(
            "Broadcast done: sent=%d failed=%d total=%d",
            result.sent,
            result.failed,
            result.total,
        )
        await reply.answer(
            _format_result(result),
            parse_mode="HTML",
            reply_markup=_menu(personnel),
        )
    finally:
        _broadcast_in_progress.discard(user_id)


async def _show_preview(message: Message, bot: Bot) -> None:
    recipients = await SheetsAsync.get_broadcast_recipients()
    if not recipients:
        await message.answer(
            "⚠️ هیچ کاربری با شناسه تلگرام در Personnel یافت نشد.\n"
            "هر عضو باید <code>telegram_id</code> داشته باشد.",
            parse_mode="HTML",
        )
        return

    me = await bot.get_me()
    body = build_changelog_announcement(bot_name=me.full_name)
    names_preview = ", ".join(p.name for p in recipients[:8])
    if len(recipients) > 8:
        names_preview += f" … (+{len(recipients) - 8})"

    await message.answer(
        "📋 <b>اعلان بروزرسانی</b>\n\n"
        f"👥 <b>{len(recipients)}</b> نفر پیام را در چت خصوصی ربات می‌گیرند:\n"
        f"<i>{names_preview}</i>\n\n"
        "برای ارسال یکی از این کارها را انجام دهید:\n"
        "• دکمه «✅ تأیید و ارسال برای همه» (منوی پایین)\n"
        "• دکمه inline همین پیام\n"
        "• دستور <code>/announce_send</code>",
        reply_markup=announce_confirm_reply_keyboard(),
        parse_mode="HTML",
    )
    await message.answer(
        body,
        parse_mode="HTML",
        reply_markup=announce_confirm_inline_keyboard(),
    )


@router.message(Command("announce"))
async def cmd_announce_preview(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    try:
        if not await _is_senior_admin_user(message.from_user.id):
            await message.answer("فقط مدیر ارشد می‌تواند اعلان بروزرسانی را ارسال کند.")
            return
        await _show_preview(message, bot)
    except Exception:
        logger.exception("announce preview failed")
        await message.answer("❌ خطا در نمایش پیش‌نمایش اعلان.", parse_mode="HTML")


@router.message(Command("announce_send"))
async def cmd_announce_send(message: Message, bot: Bot) -> None:
    if message.from_user is None:
        return
    if not await _is_senior_admin_user(message.from_user.id):
        await message.answer("فقط مدیر ارشد می‌تواند اعلان بروزرسانی را ارسال کند.")
        return
    await _execute_broadcast(message, bot)


@router.message(F.text == CONFIRM_ANNOUNCE_BUTTON)
async def confirm_announce_button(message: Message, bot: Bot) -> None:
    if message.from_user is None or not await _is_senior_admin_user(message.from_user.id):
        return
    logger.info("Announce confirm via reply keyboard from %s", message.from_user.id)
    await _execute_broadcast(message, bot)


@router.message(F.text == CANCEL_ANNOUNCE_BUTTON)
async def cancel_announce_button(message: Message) -> None:
    if message.from_user is None or not await _is_senior_admin_user(message.from_user.id):
        return
    auth = await authorize(message.from_user.id)
    await message.answer("❌ ارسال اعلان لغو شد.", reply_markup=_menu(auth.personnel))


@router.callback_query(F.data.in_({"announce:confirm", "announce:cancel"}) | F.data.startswith("announce:send:"))
async def announce_callback(callback: CallbackQuery, bot: Bot) -> None:
    if callback.from_user is None:
        await callback.answer("خطا", show_alert=True)
        return

    data = callback.data or ""

    if data == "announce:cancel":
        if not await _is_senior_admin_user(callback.from_user.id):
            await callback.answer("دسترسی ندارید.", show_alert=True)
            return
        auth = await authorize(callback.from_user.id)
        if callback.message is not None:
            await callback.message.answer("❌ ارسال اعلان لغو شد.", reply_markup=_menu(auth.personnel))
        await callback.answer()
        return

    if not await _is_senior_admin_user(callback.from_user.id):
        await callback.answer("دسترسی ندارید.", show_alert=True)
        return

    logger.info("Announce confirm via callback %s from %s", data, callback.from_user.id)
    await callback.answer("در حال ارسال…")

    if callback.message is None:
        return

    try:
        await callback.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass

    await _execute_broadcast(callback.message, bot)
