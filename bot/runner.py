"""Resilient process entrypoint.

The previous outage was caused by a container that exited immediately and was
restarted dozens of times per second, pinning the host CPU to load ~140.

This wrapper guarantees that *any* fatal error (including import/config errors)
results in a delayed exit, so the orchestrator's restart loop can never become a
tight, CPU-burning loop. It is intentionally dependency-free and import-safe.
"""

from __future__ import annotations

import logging
import os
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("runner")


def _fatal_delay() -> int:
    try:
        return max(5, int(os.getenv("FATAL_RESTART_DELAY", "20")))
    except ValueError:
        return 20


def main() -> int:
    try:
        from bot.main import main as run_bot

        run_bot()
        return 0
    except (KeyboardInterrupt, SystemExit):
        logger.info("Shutdown requested.")
        return 0
    except BaseException as exc:  # noqa: BLE001 - last-resort guard
        delay = _fatal_delay()
        logger.exception("Fatal error, sleeping %ss before exit to avoid crash loop: %s", delay, exc)
        time.sleep(delay)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
