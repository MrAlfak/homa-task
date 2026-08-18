#!/usr/bin/env python3
"""Force Dockerfile replace + redeploy."""

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
    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n", encoding="utf-8")
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )

    files = [
        ("Dockerfile", "create"),
        ("build_id.txt", "update"),
        ("bot/__init__.py", "update"),
        ("bot/handlers/employee_tasks.py", "update"),
        ("bot/main.py", "update"),
    ]
    for rel, patch_type in files:
        api("POST", "patch.saveFileAsPatch", {
            "id": APP,
            "type": "application",
            "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": patch_type,
        })
        print("uploaded", rel, patch_type)

    for i in range(4):
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
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "dockerImage": f"{app_name}:latest",
    })
    print("redeploy ...")
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"Force Dockerfile {build_id}",
        "description": "force_dockerfile_deploy.py",
    })
    time.sleep(100)
    deps = api("GET", f"deployment.allByType?id={APP}&type=application")
    dep = deps[0]
    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = log if isinstance(log, str) else str(log)
    if text.startswith('"'):
        text = json.loads(text)
    print(text[-5000:])
    ok = "grep -q" in text and "employee_tasks" in text
    print("BUILD_HAS_GREP=", ok, "status=", dep.get("status"))
    return 0 if ok and dep.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
