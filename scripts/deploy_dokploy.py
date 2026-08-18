#!/usr/bin/env python3
"""Upload source via Dokploy patch API and deploy (no SSH required)."""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

API_BASE = os.environ.get("DOKPLOY_API_BASE", "http://217.114.40.67:3000/api")
API_KEY = os.environ.get(
    "DOKPLOY_API_KEY",
    "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR",
)
APP_ID = os.environ.get("DOKPLOY_APP_ID", "yJuZ9FANN1ctYrbdtFa3W")
ROOT = Path(__file__).resolve().parents[1]

UPLOAD_FILES = [
    "build_id.txt",
    "Dockerfile",
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "bot/__init__.py",
    "bot/runner.py",
    "bot/main.py",
    "bot/proxy.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/announce.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "bot/messages/__init__.py",
    "bot/messages/changelog.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/auth.py",
]


def api(method: str, path: str, data: dict | None = None, *, timeout: int = 180) -> dict:
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
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {path}: {body_text[:500]}") from exc


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print(f"API: {API_BASE}")
    print(f"App: {APP_ID}")

    print("1) ensure patch repo ...")
    api("POST", "patch.ensureRepo", {"id": APP_ID, "type": "application"})

    print("2) upload source files ...")
    for rel in UPLOAD_FILES:
        path = ROOT / rel
        if not path.exists():
            print(f"   skip missing {rel}")
            continue
        api(
            "POST",
            "patch.saveFileAsPatch",
            {
                "id": APP_ID,
                "type": "application",
                "filePath": rel.replace("\\", "/"),
                "content": path.read_text(encoding="utf-8"),
                "patchType": "update",
            },
        )
        print(f"   uploaded {rel}")

    print("3) configure dockerfile build from patch (only when requested) ...")
    if os.environ.get("DOKPLOY_CONFIGURE", "0") == "1":
        api(
            "POST",
            "application.update",
            {
                "applicationId": APP_ID,
                "sourceType": "drop",
                "buildType": "dockerfile",
                "dockerfile": "Dockerfile",
                "dockerContextPath": ".",
                "replicas": 1,
                "memoryLimit": str(384 * 1024 * 1024),
                "memoryReservation": str(96 * 1024 * 1024),
                "cpuLimit": "500000000",
                "cpuReservation": "100000000",
                "restartPolicySwarm": {
                    "Condition": "on-failure",
                    "Delay": 10_000_000_000,
                    "MaxAttempts": 5,
                    "Window": 180_000_000_000,
                },
            },
        )

    print("4) reload drop workspace from patches ...")
    app = api("GET", f"application.one?applicationId={APP_ID}")
    if isinstance(app, dict):
        data = app.get("data", app)
        app_name = data.get("appName", "homa-task-bot-qsnkoy")
    else:
        app_name = "homa-task-bot-qsnkoy"
    api(
        "POST",
        "application.reload",
        {"applicationId": APP_ID, "appName": app_name},
    )

    print("5) redeploy (application.deploy is broken on this server; reload+redeploy applies patches) ...")
    api(
        "POST",
        "application.cleanQueues",
        {"applicationId": APP_ID},
    )
    api(
        "POST",
        "application.killBuild",
        {"applicationId": APP_ID},
    )
    api(
        "POST",
        "application.update",
        {"applicationId": APP_ID, "cleanCache": True},
    )
    api(
        "POST",
        "application.redeploy",
        {
            "applicationId": APP_ID,
            "title": "Bot deploy via patch API",
            "description": "deploy_dokploy.py (reload + redeploy)",
        },
    )
    print("DEPLOY_TRIGGERED", APP_ID)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"DEPLOY_ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
