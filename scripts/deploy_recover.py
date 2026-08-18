#!/usr/bin/env python3
"""Recover broken Dokploy patch deploy: refresh drop, re-upload, reload, deploy."""

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
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "bot/__init__.py",
    "bot/runner.py",
    "bot/main.py",
    "bot/proxy.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/middlewares/__init__.py",
    "bot/middlewares/errors.py",
    "bot/middlewares/feedback.py",
    "bot/middlewares/dedupe.py",
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
    "services/sheets_async.py",
    "services/auth.py",
]


def api(method: str, path: str, data: dict | None = None, *, timeout: int = 180) -> object:
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


def unwrap(app: object) -> dict:
    if isinstance(app, dict) and "data" in app:
        return app["data"]  # type: ignore[return-value]
    return app  # type: ignore[return-value]


def latest_dep() -> dict:
    items = api("GET", f"deployment.allByType?id={APP_ID}&type=application")
    return items[0]  # type: ignore[index]


def dep_log(dep_id: str) -> str:
    result = api("GET", f"deployment.readLogs?deploymentId={dep_id}")
    return result if isinstance(result, str) else str(result)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("1) stop + clean queues ...")
    for path, payload in [
        ("application.stop", {"applicationId": APP_ID}),
        ("application.cleanQueues", {"applicationId": APP_ID}),
        ("application.killBuild", {"applicationId": APP_ID}),
    ]:
        try:
            api("POST", path, payload)
            print(f"   ok {path}")
        except Exception as exc:  # noqa: BLE001
            print(f"   skip {path}: {exc}")

    print("2) refreshToken (recreate drop workspace) ...")
    api("POST", "application.refreshToken", {"applicationId": APP_ID})
    app = unwrap(api("GET", f"application.one?applicationId={APP_ID}"))
    print(f"   token: {app.get('refreshToken')}")

    print("3) ensure patch repo ...")
    api("POST", "patch.ensureRepo", {"id": APP_ID, "type": "application"})

    print("4) upload all source files ...")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n", encoding="utf-8")
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )
    print(f"   build_id={build_id}")
    upload_list = ["build_id.txt", "Dockerfile.deploy", *UPLOAD_FILES]
    create_files = {
        "Dockerfile.deploy",
        "services/sheets_async.py",
        "bot/middlewares/feedback.py",
        "bot/middlewares/dedupe.py",
    }
    for rel in upload_list:
        path = ROOT / rel
        if not path.exists():
            print(f"   MISSING {rel}")
            return 1
        api("POST", "patch.saveFileAsPatch", {
            "id": APP_ID,
            "type": "application",
            "filePath": rel.replace("\\", "/"),
            "content": path.read_text(encoding="utf-8"),
            "patchType": "create" if rel.replace("\\", "/") in create_files else "update",
        })
        print(f"   {rel}")

    print("5) reload drop from patches (three times) ...")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")
    for i in range(3):
        api("POST", "application.reload", {
            "applicationId": APP_ID,
            "appName": app_name,
        })
        print(f"   reload {i + 1}/3")
        time.sleep(10)

    print("5b) re-upload critical files + reload ...")
    for rel in (
        "Dockerfile.deploy",
        "build_id.txt",
        "bot/main.py",
        "services/sheets_async.py",
        "bot/handlers/admin_tasks.py",
        "bot/__init__.py",
    ):
        path = ROOT / rel
        api("POST", "patch.saveFileAsPatch", {
            "id": APP_ID,
            "type": "application",
            "filePath": rel.replace("\\", "/"),
            "content": path.read_text(encoding="utf-8"),
            "patchType": "update",
        })
        print(f"   re-upload {rel}")
    for i in range(3):
        api("POST", "application.reload", {
            "applicationId": APP_ID,
            "appName": app_name,
        })
        time.sleep(10)

    print("6) configure build (Dockerfile.deploy + cleanCache) ...")
    api("POST", "application.update", {
        "applicationId": APP_ID,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile.deploy",
        "dockerContextPath": ".",
        "dockerImage": f"{app_name}:latest",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "applicationStatus": "idle",
        "replicas": 1,
    })
    time.sleep(5)

    print("7) redeploy ...")
    api("POST", "application.redeploy", {
        "applicationId": APP_ID,
        "title": f"Async responsiveness fix {build_id}",
        "description": "deploy_recover.py",
    })
    time.sleep(100)
    dep = latest_dep()
    status = dep.get("status", "?")
    log = dep_log(dep["deploymentId"])
    print("\n--- REDEPLOY LOG (tail) ---")
    safe = log[-6000:] if len(log) > 6000 else log
    print(safe.encode("ascii", errors="replace").decode("ascii"))

    log_text = log.replace("\\n", "\n")
    ok = "grep -q" in log_text and "sheets_async" in log_text
    if ok:
        print("\nOK: Dockerfile.deploy sheets_async guard ran in build")
    else:
        print("\nWARN: build log missing sheets_async guard — drop may be stale")

    time.sleep(25)
    rt = api("GET", f"application.readLogs?applicationId={APP_ID}&tail=80")
    rt_text = rt if isinstance(rt, str) else str(rt)
    if rt_text.startswith('"'):
        rt_text = json.loads(rt_text)
    print("Handlers loaded ->", "Handlers loaded" in rt_text)
    print("Sheets cache warmed ->", "Sheets cache warmed" in rt_text)
    print(rt_text[-2500:].encode("ascii", errors="replace").decode("ascii"))

    app2 = unwrap(api("GET", f"application.one?applicationId={APP_ID}"))
    print(f"\napp status: {app2.get('applicationStatus')}")

    if status == "done" and ok:
        print("DEPLOY_OK")
        return 0

    print("DEPLOY_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
