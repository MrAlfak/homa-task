#!/usr/bin/env python3
"""Refresh drop workspace and deploy via application.deploy (not redeploy)."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"
ROOT = Path(__file__).resolve().parents[1]

FILES = [
    "build_id.txt", "Dockerfile", "requirements.txt", "config.py", ".dockerignore",
    "bot/__init__.py", "bot/runner.py", "bot/main.py", "bot/proxy.py", "bot/keyboards.py",
    "bot/states.py",
    "bot/middlewares/__init__.py", "bot/middlewares/errors.py",
    "bot/middlewares/feedback.py", "bot/middlewares/dedupe.py",
    "bot/handlers/__init__.py", "bot/handlers/start.py", "bot/handlers/announce.py",
    "bot/handlers/admin_tasks.py", "bot/handlers/employee_tasks.py", "bot/handlers/ideas.py",
    "bot/messages/__init__.py", "bot/messages/changelog.py",
    "services/__init__.py", "services/sheets.py", "services/sheets_async.py", "services/auth.py",
]


def api(method: str, path: str, data: dict | None = None) -> object:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}/{path}",
        data=body,
        method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n", encoding="utf-8")
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )

    for path, payload in [
        ("application.stop", {"applicationId": APP}),
        ("application.cleanQueues", {"applicationId": APP}),
        ("application.killBuild", {"applicationId": APP}),
    ]:
        try:
            api("POST", path, payload)
            print("ok", path)
        except Exception as exc:
            print("skip", path, exc)

    print("refreshToken ...")
    api("POST", "application.refreshToken", {"applicationId": APP})
    api("POST", "patch.ensureRepo", {"id": APP, "type": "application"})

    print("upload patches (all create) ...")
    for rel in FILES:
        api("POST", "patch.saveFileAsPatch", {
            "id": APP, "type": "application", "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": "create",
        })
        print(" ", rel)

    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy") if isinstance(app, dict) else "homa-task-bot-qsnkoy"

    print("reload x8 ...")
    for i in range(8):
        api("POST", "application.reload", {"applicationId": APP, "appName": app_name})
        print(" reload", i + 1)
        time.sleep(15)

    api("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "dockerImage": f"{app_name}:latest",
        "applicationStatus": "idle",
    })

    print("application.deploy ...")
    api("POST", "application.deploy", {
        "applicationId": APP,
        "title": f"Deploy async fix {build_id}",
        "description": "deploy_via_deploy.py",
    })

    dep = {}
    for i in range(40):
        time.sleep(5)
        deps = api("GET", f"deployment.allByType?id={APP}&type=application")
        dep = deps[0]
        status = dep.get("status", "?")
        print(" poll", i + 1, status)
        if status in {"done", "error"}:
            break

    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = json.loads(log) if isinstance(log, str) and log.startswith('"') else (log if isinstance(log, str) else str(log))
    print(text[-6000:])
    ok = "grep -q" in text and "sheets_async" in text
    print("BUILD_OK=", ok, "status=", dep.get("status"))

    time.sleep(20)
    rt = api("GET", f"application.readLogs?applicationId={APP}&tail=80")
    rt_text = json.loads(rt) if isinstance(rt, str) and rt.startswith('"') else (rt if isinstance(rt, str) else str(rt))
    for needle in ("Handlers loaded", "Sheets cache warmed"):
        print(needle, "->", needle in rt_text)
    print(rt_text[-2000:])
    return 0 if ok and dep.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
