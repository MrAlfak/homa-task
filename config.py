"""Application configuration loaded from environment variables."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


def _app_dir() -> Path:
    """Directory that holds .env next to source or a frozen/Windows exe."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = _app_dir()
load_dotenv(BASE_DIR / "homa.env")
load_dotenv(BASE_DIR / ".env")
load_dotenv()


def _resolve_credentials_path() -> Path:
    """Load Google credentials from file path or JSON env (for Dokploy)."""
    json_payload = os.getenv("GOOGLE_CREDENTIALS_JSON", "").strip()
    if json_payload:
        parsed = json.loads(json_payload)
        default_target = Path(tempfile.gettempdir()) / "google-service-account.json"
        target = Path(os.getenv("GOOGLE_CREDENTIALS_PATH", str(default_target)))
        if not target.is_absolute():
            target = BASE_DIR / target
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(parsed), encoding="utf-8")
        try:
            os.chmod(target, 0o600)
        except OSError:
            pass
        return target

    credentials_path = Path(
        os.getenv("GOOGLE_CREDENTIALS_PATH", "credentials/google-service-account.json")
    )
    if not credentials_path.is_absolute():
        credentials_path = BASE_DIR / credentials_path
    return credentials_path


def _webhook_secret(bot_token: str) -> str:
    explicit = os.getenv("WEBHOOK_SECRET", "").strip()
    if explicit:
        return explicit
    return hashlib.sha256(f"homa-webhook:{bot_token}".encode()).hexdigest()[:32]


@dataclass(frozen=True)
class Config:
    """Runtime configuration for the Telegram bot and Google Sheets."""

    bot_token: str
    google_sheet_id: str
    google_credentials_path: Path
    bot_mode: str
    webhook_host: str
    webhook_path: str
    webhook_port: int
    webhook_secret: str
    group_chat_id: int | None
    fsm_path: Path
    sms_api_key: str
    sms_api_url: str

    @property
    def google_sheet_url(self) -> str:
        return f"https://docs.google.com/spreadsheets/d/{self.google_sheet_id}/edit"

    @classmethod
    def from_env(cls) -> Config:
        bot_token = os.getenv("BOT_TOKEN", "").strip()
        google_sheet_id = os.getenv("GOOGLE_SHEET_ID", "").strip()
        credentials_path = _resolve_credentials_path()

        bot_mode = os.getenv("BOT_MODE", "polling").strip().lower()
        webhook_host = os.getenv("WEBHOOK_HOST", "").strip().rstrip("/")
        webhook_path = os.getenv("WEBHOOK_PATH", "/webhook").strip()
        webhook_port = int(os.getenv("WEBHOOK_PORT", "8080"))
        group_raw = os.getenv("GROUP_CHAT_ID", "").strip()
        group_chat_id = int(group_raw) if group_raw else None
        fsm_raw = os.getenv("FSM_PATH", "").strip()
        if fsm_raw:
            fsm_path = Path(fsm_raw)
            if not fsm_path.is_absolute():
                fsm_path = BASE_DIR / fsm_path
        elif os.name == "nt":
            fsm_path = BASE_DIR / "homa_fsm.json"
        else:
            fsm_path = Path("/tmp/homa_fsm.json")

        if not bot_token:
            raise ValueError("BOT_TOKEN is required.")
        if not google_sheet_id:
            raise ValueError("GOOGLE_SHEET_ID is required.")
        if not credentials_path.exists():
            raise FileNotFoundError(
                f"Google credentials not found at {credentials_path}. "
                "Set GOOGLE_CREDENTIALS_JSON or mount credentials file."
            )

        return cls(
            bot_token=bot_token,
            google_sheet_id=google_sheet_id,
            google_credentials_path=credentials_path,
            bot_mode=bot_mode,
            webhook_host=webhook_host,
            webhook_path=webhook_path,
            webhook_port=webhook_port,
            webhook_secret=_webhook_secret(bot_token),
            group_chat_id=group_chat_id,
            fsm_path=fsm_path,
            sms_api_key=os.getenv("SMS_API_KEY", "").strip(),
            sms_api_url=os.getenv(
                "SMS_API_URL",
                "https://mydnspanel.com/webservice/server",
            ).strip()
            or "https://mydnspanel.com/webservice/server",
        )


config = Config.from_env()
