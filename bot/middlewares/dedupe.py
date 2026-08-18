"""Drop duplicate menu taps and serialize per-user handler execution.

Two related problems this middleware fixes:

1. **Exact-repeat spam**: the same text/callback arriving twice within a
   short window (double-tap, Telegram retry, etc.) — dropped as before.
2. **Slow-retap pile-up**: if a Sheets call is momentarily slow (rate limit,
   network blip), an impatient user re-taps *after* the short dedupe window
   has elapsed. Previously this launched a *second, concurrent* run of the
   same handler for that user — doubling Sheets API load exactly when it was
   already struggling, and risking duplicate task/idea rows. Now, while a
   user's previous update is still being processed, any new update from that
   same user is held off (with a light "still working" hint) instead of
   starting a concurrent run. A stale-lock timeout guarantees a user can
   never get permanently stuck if a handler hangs.

IMPORTANT: register a single shared instance for both ``dp.message`` and
``dp.callback_query`` (see ``bot/main.py``) so the busy-lock covers a user
across *both* event types — otherwise a reply-keyboard tap and an inline
button tap from the same user could still run concurrently.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

# Safety valve: if a handler is somehow still "busy" after this long (should
# never happen — Sheets calls have their own retry/timeout), stop blocking the
# user rather than locking them out until a restart.
BUSY_STALE_AFTER_SEC = 25.0

# Periodic cleanup so the per-user dicts don't grow forever over a long
# uptime (they're process memory only, never persisted).
_SWEEP_INTERVAL_SEC = 300.0
_ENTRY_MAX_AGE_SEC = 900.0

_BUSY_HINT = "⏳ درخواست قبلی شما هنوز در حال پردازش است، چند لحظه صبر کنید."


class DuplicateTapMiddleware(BaseMiddleware):
    """Ignore identical repeats and serialize handler execution per user."""

    def __init__(self, window_seconds: float = 2.5) -> None:
        self.window = window_seconds
        self._last_message: dict[int, tuple[str, float]] = {}
        self._last_callback: dict[int, tuple[str, float]] = {}
        self._busy_since: dict[int, float] = {}
        self._last_swept = time.monotonic()

    @staticmethod
    def _user_id(event: TelegramObject) -> int | None:
        if isinstance(event, (Message, CallbackQuery)) and event.from_user:
            return event.from_user.id
        return None

    def _sweep_if_due(self, now: float) -> None:
        if now - self._last_swept < _SWEEP_INTERVAL_SEC:
            return
        self._last_swept = now
        cutoff = now - _ENTRY_MAX_AGE_SEC
        for tracker in (self._last_message, self._last_callback):
            stale = [uid for uid, (_, ts) in tracker.items() if ts < cutoff]
            for uid in stale:
                tracker.pop(uid, None)
        stale_busy = [uid for uid, ts in self._busy_since.items() if ts < cutoff]
        for uid in stale_busy:
            self._busy_since.pop(uid, None)

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        now = time.monotonic()
        self._sweep_if_due(now)

        if isinstance(event, Message) and event.from_user and event.text:
            uid = event.from_user.id
            key = event.text.strip()
            prev = self._last_message.get(uid)
            if prev and prev[0] == key and (now - prev[1]) < self.window:
                logger.info("Ignored duplicate message from %s: %r", uid, key[:40])
                return None
            self._last_message[uid] = (key, now)

        elif isinstance(event, CallbackQuery) and event.from_user and event.data:
            uid = event.from_user.id
            key = event.data
            prev = self._last_callback.get(uid)
            if prev and prev[0] == key and (now - prev[1]) < self.window:
                await event.answer()
                logger.info("Ignored duplicate callback from %s: %s", uid, key)
                return None
            self._last_callback[uid] = (key, now)

        uid = self._user_id(event)
        if uid is not None:
            busy_since = self._busy_since.get(uid)
            if busy_since is not None and (now - busy_since) < BUSY_STALE_AFTER_SEC:
                logger.info("Holding off update from %s: previous action still running", uid)
                if isinstance(event, CallbackQuery):
                    try:
                        await event.answer(_BUSY_HINT)
                    except Exception:
                        pass
                elif isinstance(event, Message):
                    try:
                        await event.answer(_BUSY_HINT)
                    except Exception:
                        pass
                return None
            self._busy_since[uid] = now

        try:
            return await handler(event, data)
        finally:
            if uid is not None:
                self._busy_since.pop(uid, None)
