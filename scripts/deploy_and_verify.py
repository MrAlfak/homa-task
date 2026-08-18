#!/usr/bin/env python3
"""Upload patches, deploy, poll status, print build log."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API_BASE = "http://217.114.40.67:3000/api"
API_KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP_ID = "yJuZ9FANN1ctYrbdtFa3W"
ROOT = Path(__file__).resolve().parents[1]

UPLOAD_FILES = [
    "Dockerfile",
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "build_id.txt",
    "bot/__init__.py",
    "bot/runner.py",
    "bot/main.py",
    "bot/proxy.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/formatting.py",
    "bot/create_task_flow.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/announce.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "bot/middlewares/__init__.py",
    "bot/middlewares/dedupe.py",
    "bot/middlewares/errors.py",
    "bot/middlewares/feedback.py",
    "bot/messages/__init__.py",
    "bot/messages/changelog.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/sheets_async.py",
    "services/auth.py",
]


def api(method: str, path: str, data: dict | None = None, *, timeout: int = 180) -> dict | list | str:
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
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def latest_deployment() -> dict:
    items = api("GET", f"deployment.allByType?id={APP_ID}&type=application")
    if not isinstance(items, list) or not items:
        raise RuntimeError("No deployments returned")
    return items[0]


def deployment_log(deployment_id: str) -> str:
    result = api("GET", f"deployment.readLogs?deploymentId={deployment_id}")
    return result if isinstance(result, str) else str(result)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("1) clean queues + kill build ...")
    api("POST", "application.cleanQueues", {"applicationId": APP_ID})
    api("POST", "application.killBuild", {"applicationId": APP_ID})

    print("2) ensure patch repo ...")
    api("POST", "patch.ensureRepo", {"id": APP_ID, "type": "application"})

    print("3) upload files ...")
    for rel in UPLOAD_FILES:
        path = ROOT / rel
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
        print(f"   {rel}")

    print("3) reload patch workspace ...")
    app = api("GET", f"application.one?applicationId={APP_ID}")
    if isinstance(app, dict):
        data = app.get("data", app)
        app_name = data.get("appName", "homa-task-bot-qsnkoy")
        api(
            "POST",
            "application.reload",
            {"applicationId": APP_ID, "appName": app_name},
        )

    print("4) redeploy (reload syncs patches; deploy endpoint fails on this server) ...")
    api("POST", "application.update", {"applicationId": APP_ID, "cleanCache": True})
    api(
        "POST",
        "application.redeploy",
        {
            "applicationId": APP_ID,
            "title": "Fix /start during task create + broadcast",
            "description": "build 1783607708 — create_task_flow, admin_tasks hardening",
        },
    )

    dep: dict | None = None
    for attempt in range(36):
        time.sleep(5)
        dep = latest_deployment()
        status = dep.get("status", "?")
        dep_id = dep.get("deploymentId", "?")
        print(f"   poll {attempt + 1}: {status} ({dep_id})")
        if status in {"done", "error"}:
            break

    if dep is None:
        print("DEPLOY_TIMEOUT")
        return 1

    log = deployment_log(dep["deploymentId"])
    print("\n--- BUILD LOG (tail) ---")
    print(log[-4000:] if len(log) > 4000 else log)

    app = api("GET", f"application.one?applicationId={APP_ID}")
    if isinstance(app, dict):
        data = app.get("data", app)
        print(f"\napp status: {data.get('applicationStatus')}")

    if dep.get("status") != "done":
        print("DEPLOY_FAILED")
        return 1

    print("DEPLOY_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
