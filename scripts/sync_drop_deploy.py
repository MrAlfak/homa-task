#!/usr/bin/env python3
"""Upload patches FIRST, then refreshToken + reload (correct Dokploy order)."""

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
    "bot/middlewares/__init__.py",
    "bot/middlewares/errors.py",
    "bot/middlewares/feedback.py",
    "bot/middlewares/dedupe.py",
    "bot/handlers/__init__.py", "bot/handlers/start.py",
    "bot/handlers/announce.py", "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py", "bot/handlers/ideas.py",
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

    api("POST", "application.stop", {"applicationId": APP})
    api("POST", "patch.ensureRepo", {"id": APP, "type": "application"})

    print("1) upload patches ...")
    for rel in FILES:
        api("POST", "patch.saveFileAsPatch", {
            "id": APP, "type": "application", "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": "update",
        })
        print(" ", rel)

    print("2) refreshToken ...")
    api("POST", "application.refreshToken", {"applicationId": APP})
    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")
    print("   token:", app.get("refreshToken"))

    print("3) reload x5 ...")
    for i in range(5):
        api("POST", "application.reload", {"applicationId": APP, "appName": app_name})
        print("   reload", i + 1)
        time.sleep(15)

    api("POST", "application.saveBuildType", {
        "applicationId": APP,
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "dockerBuildStage": None,
        "herokuVersion": None,
        "railpackVersion": None,
    })
    api("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "dockerImage": f"{app_name}:latest",
    })

    print("4) redeploy ...")
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"Upload-first sync {build_id}",
        "description": "sync_drop_deploy.py",
    })
    time.sleep(110)
    deps = api("GET", f"deployment.allByType?id={APP}&type=application")
    dep = deps[0]
    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = json.loads(log) if isinstance(log, str) and log.startswith('"') else (log if isinstance(log, str) else str(log))
    print(text[-4500:])
    ok = "grep -q" in text and "sheets_async" in text
    print("\nBUILD_HAS_ANNOUNCE_GUARD=", ok, "status=", dep.get("status"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
