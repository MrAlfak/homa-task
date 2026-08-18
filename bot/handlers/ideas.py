"""Ideas — submit and view team ideas."""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.formatting import esc
from bot.keyboards import IDEAS_TEXTS, cancel_idea_keyboard, ideas_menu_keyboard
from bot.states import IdeaStates
from services.sheets_async import SheetsAsync, authorize

router = Router(name="ideas")


@router.message(F.text.in_(IDEAS_TEXTS))
async def ideas_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    if message.from_user is None:
        return

    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await message.answer(auth.reason, parse_mode="HTML")
        return

    sheet_url = await SheetsAsync.get_ideas_sheet_url()
    await message.answer(
        "💡 <b>بخش ایده‌ها</b>\n\n"
        "همه مدیران و کارمندان می‌توانند ایده ثبت کنند.\n"
        "نام ثبت‌کننده در Google Sheet ذخیره می‌شود.",
        reply_markup=ideas_menu_keyboard(sheet_url),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "idea:new")
async def start_new_idea(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.from_user is None or callback.message is None:
        return

    await callback.answer()

    auth = await authorize(callback.from_user.id)
    if not auth.allowed:
        await callback.message.answer("دسترسی ندارید.")
        return

    await state.set_state(IdeaStates.entering_idea)
    await callback.message.answer(
        "💡 ایده خود را بنویسید:\n"
        "(حداقل ۵ کاراکتر)",
        reply_markup=cancel_idea_keyboard(),
    )


@router.message(IdeaStates.entering_idea, F.text)
async def save_idea(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return

    auth = await authorize(message.from_user.id)
    if not auth.allowed or auth.personnel is None:
        await state.clear()
        await message.answer(auth.reason, parse_mode="HTML")
        return

    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("ایده باید حداقل ۵ کاراکتر باشد. دوباره بنویسید:")
        return

    data = await state.get_data()
    if data.get("idea_submitting") or data.get("idea_submitted"):
        return

    await state.update_data(idea_submitting=True)

    try:
        idea = await SheetsAsync.create_idea(auth.personnel, text)
    except Exception:
        await state.update_data(idea_submitting=False)
        await message.answer("⚠️ ثبت ایده ناموفق بود. لطفاً دوباره تلاش کنید.")
        return

    await state.update_data(idea_submitted=True)
    await state.clear()

    await message.answer(
        f"✅ ایده ثبت شد!\n\n"
        f"💡 {esc(idea.text)}\n"
        f"👤 ثبت‌کننده: {esc(idea.created_by)} ({esc(idea.role)})\n"
        f"📅 {esc(idea.created_at)}\n\n"
        "در تب <b>Ideas</b> در Google Sheet قابل مشاهده است.",
        parse_mode="HTML",
    )


@router.callback_query(F.data == "idea:list")
async def list_ideas(callback: CallbackQuery) -> None:
    if callback.message is None or callback.from_user is None:
        return

    await callback.answer()

    auth = await authorize(callback.from_user.id)
    if not auth.allowed:
        await callback.message.answer("دسترسی ندارید.")
        return

    ideas = await SheetsAsync.get_recent_ideas(limit=15)
    if not ideas:
        await callback.message.answer("هنوز ایده‌ای ثبت نشده.")
        return

    # Telegram caps a single message at 4096 characters. Even with a 120-char
    # preview per idea, long names/dates across 15 ideas can add up, so build
    # the message incrementally and stop (with a note) before hitting the
    # limit instead of letting the whole send fail.
    MAX_MESSAGE_CHARS = 3800
    header = "📋 <b>آخرین ایده‌ها:</b>\n"
    lines = [header]
    total_len = len(header)
    shown = 0
    for index, idea in enumerate(ideas, start=1):
        preview = idea.text if len(idea.text) <= 120 else idea.text[:117] + "..."
        entry = (
            f"{index}. {esc(preview)}\n"
            f"   👤 {esc(idea.created_by)} ({esc(idea.role)}) — 📅 {esc(idea.created_at)}"
        )
        if total_len + len(entry) + 2 > MAX_MESSAGE_CHARS:
            break
        lines.append(entry)
        total_len += len(entry) + 2
        shown += 1

    remaining = len(ideas) - shown
    if remaining > 0:
        lines.append(f"… و {remaining} ایده دیگر (در Google Sheet مشاهده کنید).")

    sheet_url = await SheetsAsync.get_ideas_sheet_url()
    await callback.message.answer(
        "\n\n".join(lines),
        reply_markup=ideas_menu_keyboard(sheet_url),
        parse_mode="HTML",
    )


@router.callback_query(F.data == "idea:cancel")
async def cancel_idea(callback: CallbackQuery, state: FSMContext) -> None:
    await callback.answer()
    await state.clear()
    if callback.message:
        await callback.message.answer("❌ ثبت ایده لغو شد.")
