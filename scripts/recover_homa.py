#!/usr/bin/env python3
"""Stop crash-looping Homa bot and redeploy without VLESS/sing-box."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("DOKPLOY_API_BASE", "https://blob.firstdata.ir/api")
API_KEY = os.environ.get(
    "DOKPLOY_API_KEY",
    "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR",
)
APP_ID = "ZTVQekZHYAAgnDEQD90mT"
ROOT = Path(__file__).resolve().parents[1]

UPLOAD_FILES = [
    "Dockerfile",
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "bot/__init__.py",
    "bot/main.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/auth.py",
]

DELETE_FILES = [
    "entrypoint.sh",
    "scripts/vless_parser.py",
    "scripts/setup_proxy.py",
    "scripts/generate_singbox_config.py",
]


def api(method: str, path: str, data: dict | None = None, *, timeout: int = 120) -> dict:
    url = f"{API_BASE}/{path}"
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        url,
        data=body,
        method=method,
        headers={
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def unwrap(result: dict) -> dict:
    if isinstance(result, dict) and "data" in result:
        return result["data"]
    return result


def build_env() -> str:
    creds_path = ROOT / "credentials" / "google-service-account.json"
    creds_json = json.dumps(json.loads(creds_path.read_text(encoding="utf-8")), separators=(",", ":"))
    token = os.environ.get("BOT_TOKEN", "").strip()
    if not token:
        env_file = ROOT / ".env"
        if env_file.is_file():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                if line.startswith("BOT_TOKEN="):
                    token = line.split("=", 1)[1].strip()
                    break
    sheet_id = os.environ.get("GOOGLE_SHEET_ID", "1-JjUkuQm7D5pSHsm_ssrSw-u9588FJeYwzjJ4sli4Uk")
    return (
        f"BOT_TOKEN={token}\n"
        f"GOOGLE_SHEET_ID={sheet_id}\n"
        f"GOOGLE_CREDENTIALS_JSON={creds_json}\n"
        "GOOGLE_CREDENTIALS_PATH=/tmp/google-service-account.json\n"
        "BOT_MODE=polling\n"
    )


def main() -> int:
    print("1) Stop application (free server from crash loop)...")
    try:
        api("POST", "application.stop", {"applicationId": APP_ID})
        print("   stopped")
    except Exception as exc:
        print(f"   stop failed (continuing): {exc}")

    print("2) Clean environment (no proxy vars)...")
    env = build_env()
    api(
        "POST",
        "application.saveEnvironment",
        {
            "applicationId": APP_ID,
            "env": env,
            "buildArgs": None,
            "buildSecrets": None,
            "createEnvFile": True,
        },
        timeout=180,
    )
    print("   env saved")

    print("3) Upload clean source files...")
    for rel in UPLOAD_FILES:
        path = ROOT / rel
        content = path.read_text(encoding="utf-8")
        api(
            "POST",
            "patch.saveFileAsPatch",
            {
                "id": APP_ID,
                "type": "application",
                "filePath": rel.replace("\\", "/"),
                "content": content,
                "patchType": "update",
            },
            timeout=180,
        )
        print(f"   uploaded {rel}")

    print("4) Remove VLESS/proxy files from patch repo...")
    for rel in DELETE_FILES:
        try:
            api(
                "POST",
                "patch.markFileForDeletion",
                {"id": APP_ID, "type": "application", "filePath": rel},
            )
            print(f"   marked delete {rel}")
        except Exception as exc:
            print(f"   skip delete {rel}: {exc}")

    print("5) Ensure dockerfile build (no entrypoint)...")
    api(
        "POST",
        "application.update",
        {
            "applicationId": APP_ID,
            "sourceType": "drop",
            "buildType": "dockerfile",
            "dockerfile": "Dockerfile",
            "dockerContextPath": ".",
            "createEnvFile": True,
        },
        timeout=120,
    )

    print("6) Deploy clean bot...")
    api(
        "POST",
        "application.deploy",
        {
            "applicationId": APP_ID,
            "title": "Remove VLESS - restore direct network",
            "description": "No sing-box, no proxy, simple python bot",
        },
        timeout=120,
    )
    print("DONE — deploy triggered")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")[:500]
        print(f"HTTP {exc.code}: {body}", file=sys.stderr)
        raise SystemExit(1) from exc
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
