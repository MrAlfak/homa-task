#!/usr/bin/env python3
"""Send changelog announcement to all Personnel (local fallback when deploy is stuck).

Usage:
  python scripts/broadcast_local.py
  python scripts/broadcast_local.py --dry-run
  python scripts/broadcast_local.py --send
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.messages.changelog import build_changelog_announcement
from bot.proxy import start_proxy
from config import config
from services.sheets import get_sheets_service


async def run(*, dry_run: bool, send: bool) -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sheets = get_sheets_service()
    recipients = sheets.get_broadcast_recipients()
    if not recipients:
        print("No recipients with telegram_id in Personnel.")
        return 1

    me_name = "Team Management Homa"
    body = build_changelog_announcement(bot_name=me_name)

    print(f"Recipients ({len(recipients)}):")
    for person in recipients:
        print(f"  - {person.name} ({person.telegram_id})")

    if dry_run or not send:
        print("\n--- message preview ---")
        print(body.replace("<b>", "").replace("</b>", "").replace("<code>", "").replace("</code>", ""))
        print("\nDry run only. Re-run with --send to broadcast.")
        return 0

    proxy_url = start_proxy()
    session = None
    if proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession

        session = AiohttpSession(proxy=proxy_url)
        print(f"Using proxy: {proxy_url}")

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )

    sent = 0
    failed = 0
    try:
        me = await bot.get_me()
        body = build_changelog_announcement(bot_name=me.full_name)
        for person in recipients:
            try:
                await bot.send_message(person.telegram_id, body, parse_mode="HTML")
                sent += 1
                print(f"OK  {person.name}")
                await asyncio.sleep(0.08)
            except Exception as exc:
                failed += 1
                print(f"ERR {person.name}: {exc}")
    finally:
        await bot.session.close()

    print(f"\nDone: sent={sent} failed={failed} total={len(recipients)}")
    return 0 if failed == 0 else 2


def main() -> int:
    parser = argparse.ArgumentParser(description="Broadcast bot update to all Personnel")
    parser.add_argument("--dry-run", action="store_true", help="List recipients + preview only")
    parser.add_argument("--send", action="store_true", help="Actually send messages")
    args = parser.parse_args()
    if not args.dry_run and not args.send:
        args.dry_run = True
    return asyncio.run(run(dry_run=args.dry_run, send=args.send))


if __name__ == "__main__":
    raise SystemExit(main())
