#!/usr/bin/env python3
"""Force full patch sync + Dockerfile recreate + redeploy."""

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

    print("upload all patches ...")
    for rel in FILES:
        patch_type = "create" if rel == "Dockerfile" else "update"
        api("POST", "patch.saveFileAsPatch", {
            "id": APP, "type": "application", "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": patch_type,
        })
        print(" ", rel, patch_type)

    api("POST", "application.refreshToken", {"applicationId": APP})
    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")

    for i in range(6):
        api("POST", "application.reload", {"applicationId": APP, "appName": app_name})
        print("reload", i + 1)
        time.sleep(12)

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

    print("redeploy ...")
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"Force full sync {build_id}",
        "description": "force_full_deploy.py",
    })
    time.sleep(120)

    deps = api("GET", f"deployment.allByType?id={APP}&type=application")
    dep = deps[0]
    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = json.loads(log) if isinstance(log, str) and log.startswith('"') else (log if isinstance(log, str) else str(log))
    print(text[-5000:])
    ok = "grep -q" in text and "sheets_async" in text
    print("BUILD_OK=", ok, "status=", dep.get("status"))

    time.sleep(25)
    runtime = api("GET", f"application.readLogs?applicationId={APP}&tail=60")
    rt = json.loads(runtime) if isinstance(runtime, str) and runtime.startswith('"') else (runtime if isinstance(runtime, str) else str(runtime))
    for needle in ("Handlers loaded", "Sheets cache warmed", "Running build"):
        print(needle, "->", needle in rt)
    print(rt[-2500:])
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
