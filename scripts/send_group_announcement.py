#!/usr/bin/env python3
"""Send changelog announcement to the team Telegram group (one-shot)."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from bot.messages.changelog import build_group_announcement

load_dotenv(ROOT / ".env")


async def main() -> int:
    parser = argparse.ArgumentParser(description="Send group changelog announcement.")
    parser.add_argument(
        "--chat-id",
        type=int,
        default=int(os.getenv("GROUP_CHAT_ID", "0") or "0"),
        help="Telegram group chat id (or set GROUP_CHAT_ID in .env)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print message only")
    args = parser.parse_args()

    token = os.getenv("BOT_TOKEN", "").strip()
    if not token:
        print("BOT_TOKEN is required.", file=sys.stderr)
        return 1

    message = build_group_announcement()
    if args.dry_run:
        print(message.replace("<b>", "**").replace("</b>", "**"))
        return 0

    if not args.chat_id:
        print("Provide --chat-id or set GROUP_CHAT_ID in .env", file=sys.stderr)
        return 1

    bot = Bot(
        token=token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
    try:
        me = await bot.get_me()
        sent = await bot.send_message(args.chat_id, build_group_announcement(bot_name=me.full_name))
        print(f"Sent message_id={sent.message_id} to chat_id={args.chat_id}")
    finally:
        await bot.session.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
