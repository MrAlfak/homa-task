#!/usr/bin/env python3
"""Diagnose and attempt patch-based application.deploy recovery."""

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


def api(method: str, path: str, data: dict | None = None) -> object:
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
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def latest_dep() -> dict:
    items = api("GET", f"deployment.allByType?id={APP_ID}&type=application")
    return items[0]  # type: ignore[index]


def dep_log(dep_id: str) -> str:
    return str(api("GET", f"deployment.readLogs?deploymentId={dep_id}"))


def try_deploy(label: str) -> tuple[str, str]:
    api("POST", "application.deploy", {
        "applicationId": APP_ID,
        "title": label,
        "description": "fix_patch_deploy.py",
    })
    time.sleep(12)
    dep = latest_dep()
    return dep.get("status", "?"), dep_log(dep["deploymentId"])


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    print("=== app state ===")
    app = api("GET", f"application.one?applicationId={APP_ID}")
    if isinstance(app, dict) and "data" in app:
        app = app["data"]
    print("status:", app.get("applicationStatus"), "source:", app.get("sourceType"), "token:", app.get("refreshToken"))

    print("\n=== refreshToken + ensureRepo + reload ===")
    api("POST", "application.refreshToken", {"applicationId": APP_ID})
    api("POST", "application.cleanQueues", {"applicationId": APP_ID})
    api("POST", "application.killBuild", {"applicationId": APP_ID})
    api("POST", "patch.ensureRepo", {"id": APP_ID, "type": "application"})
    app = api("GET", f"application.one?applicationId={APP_ID}")
    if isinstance(app, dict) and "data" in app:
        app = app["data"]
    api("POST", "application.reload", {"applicationId": APP_ID, "appName": app["appName"]})

    print("\n=== upload announce.py touch ===")
    content = (ROOT / "bot/handlers/announce.py").read_text(encoding="utf-8")
    api("POST", "patch.saveFileAsPatch", {
        "id": APP_ID,
        "type": "application",
        "filePath": "bot/handlers/announce.py",
        "content": content,
        "patchType": "update",
    })

    status, log = try_deploy("refresh+reload deploy test")
    print("result:", status)
    print(log)

    if status == "done" and "Applying" in log:
        print("\nPATCH DEPLOY FIXED")
        return 0

    print("\n=== update cleanCache + deploy ===")
    api("POST", "application.update", {
        "applicationId": APP_ID,
        "cleanCache": True,
        "applicationStatus": "running",
    })
    status, log = try_deploy("cleanCache deploy test")
    print("result:", status)
    print(log)

    return 1 if status != "done" else 0


if __name__ == "__main__":
    raise SystemExit(main())
