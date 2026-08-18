"""Bot entry point — polling or webhook."""

from __future__ import annotations

import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.webhook.aiohttp_server import SimpleRequestHandler, setup_application
from aiohttp import web

from bot.handlers import admin_tasks, content, employee_tasks, filming, ideas, start
from bot.middlewares.dedupe import DuplicateTapMiddleware
from bot.middlewares.errors import UserErrorMiddleware
from bot.middlewares.feedback import InstantFeedbackMiddleware

try:
    from bot.handlers import announce as _announce_module  # noqa: F401
except ImportError:
    _announce_module = None
from bot.proxy import start_proxy
from config import config
from services.overdue import overdue_supervisor
from services.sheets_async import SheetsAsync, warmup_caches

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def create_bot() -> Bot:
    session = None
    proxy_url = start_proxy()
    if proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession

        session = AiohttpSession(proxy=proxy_url)
        logger.info("Telegram session routed through proxy.")
    return Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )


def create_dispatcher() -> Dispatcher:
    dp = Dispatcher(storage=MemoryStorage())
    # Single shared instance: the per-user busy-lock must cover both message
    # and callback events, otherwise a reply-keyboard tap and an inline-button
    # tap from the same user could still run concurrently.
    dedupe_middleware = DuplicateTapMiddleware()
    dp.message.middleware(dedupe_middleware)
    dp.callback_query.middleware(dedupe_middleware)
    dp.message.middleware(InstantFeedbackMiddleware())
    dp.message.middleware(UserErrorMiddleware())
    dp.callback_query.middleware(UserErrorMiddleware())
    # announce is included via start.router (see bot/handlers/start.py).
    dp.include_router(start.router)
    dp.include_router(admin_tasks.router)
    dp.include_router(employee_tasks.router)
    dp.include_router(ideas.router)
    dp.include_router(filming.router)
    dp.include_router(content.router)
    return dp


async def wait_for_telegram(bot: Bot, attempts: int = 30, delay: float = 3.0) -> bool:
    """Block until Telegram is reachable (e.g. while the proxy warms up).

    Never raises: on timeout it returns False and lets the polling loop keep
    retrying on its own, so the container stays up regardless.
    """
    for attempt in range(1, attempts + 1):
        try:
            me = await bot.get_me()
            logger.info("Connected to Telegram as @%s", me.username)
            return True
        except Exception as exc:  # noqa: BLE001
            logger.info(
                "Waiting for Telegram connectivity (%d/%d): %s",
                attempt, attempts, type(exc).__name__,
            )
            await asyncio.sleep(delay)
    logger.warning("No confirmed connectivity yet; polling will keep retrying.")
    return False


async def _log_build_info(bot: Bot) -> None:
    """Log build stamp to verify the running container has fresh code."""
    _ = bot
    from pathlib import Path

    stamp = Path("/app/build_id.txt")
    if stamp.is_file():
        logger.info("Running build: %s", stamp.read_text(encoding="utf-8").strip())
    if _announce_module is not None:
        logger.info("Announce handler module: %s", _announce_module.__file__)


async def notify_startup(bot: Bot) -> None:
    """Notify admins that the bot was updated (best-effort, never fatal)."""
    from bot import __build__ as package_build

    try:
        me = await bot.get_me()
        message = f"✅ ربات <b>{me.full_name}</b> بروزرسانی شد.\n<code>build {package_build}</code>"
    except Exception as exc:  # noqa: BLE001
        logger.warning("Startup notify skipped (get_me failed): %s", exc)
        return

    try:
        admins = await SheetsAsync.get_active_personnel(role="admin")
    except Exception as exc:
        logger.warning("Startup notify skipped (sheets): %s", exc)
        return

    seen: set[int] = set()
    for admin in admins:
        if admin.telegram_id in seen:
            continue
        seen.add(admin.telegram_id)
        try:
            await bot.send_message(admin.telegram_id, message)
            logger.info("Startup notification sent to admin %s", admin.telegram_id)
        except Exception as exc:
            logger.warning("Could not notify admin %s: %s", admin.telegram_id, exc)


async def _warmup_on_startup(bot: Bot) -> None:
    _ = bot
    try:
        await warmup_caches()
        logger.info("Sheets cache warmed up.")
    except Exception as exc:
        logger.warning("Sheets warmup skipped: %s", exc)


async def _start_overdue_supervisor(bot: Bot) -> None:
    """Launch background overdue color + reminder loop (never blocks startup)."""
    asyncio.create_task(overdue_supervisor(bot), name="overdue-supervisor")
    logger.info("Overdue supervisor scheduled.")


async def run_polling() -> None:
    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(_warmup_on_startup)
    dp.startup.register(notify_startup)
    dp.startup.register(_log_build_info)
    dp.startup.register(_start_overdue_supervisor)
    logger.info(
        "Handlers loaded: announce, start, admin_tasks, employee_tasks, ideas, filming, content"
    )
    logger.info("Starting bot in polling mode...")
    # Give the embedded proxy time to bring a node up before polling begins.
    await wait_for_telegram(bot)
    try:
        # Long polling (30s) keeps the bot idle between updates: ~1 request per
        # 30s when there is no traffic, so CPU/network stay near zero.
        # drop_pending_updates avoids a burst of work after a restart.
        await dp.start_polling(
            bot,
            polling_timeout=30,
            drop_pending_updates=True,
        )
    finally:
        await bot.session.close()


async def run_webhook() -> None:
    if not config.webhook_host:
        raise ValueError("WEBHOOK_HOST is required when BOT_MODE=webhook")

    bot = create_bot()
    dp = create_dispatcher()
    dp.startup.register(_warmup_on_startup)
    dp.startup.register(notify_startup)
    dp.startup.register(_log_build_info)
    dp.startup.register(_start_overdue_supervisor)
    webhook_url = f"{config.webhook_host}{config.webhook_path}"

    await bot.set_webhook(webhook_url)
    app = web.Application()
    SimpleRequestHandler(dispatcher=dp, bot=bot).register(app, path=config.webhook_path)
    setup_application(app, dp, bot=bot)

    logger.info("Starting webhook on %s:%s%s", config.webhook_host, config.webhook_port, config.webhook_path)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, host="0.0.0.0", port=config.webhook_port)
    await site.start()

    try:
        await asyncio.Event().wait()
    finally:
        await bot.delete_webhook()
        await runner.cleanup()
        await bot.session.close()


def main() -> None:
    try:
        if config.bot_mode == "webhook":
            asyncio.run(run_webhook())
        else:
            asyncio.run(run_polling())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")


if __name__ == "__main__":
    main()
