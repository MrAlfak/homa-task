"""Start the bot with the app folder on sys.path (embeddable Python)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from bot.main import main

if __name__ == "__main__":
    main()
