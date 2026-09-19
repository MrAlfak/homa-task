#!/usr/bin/env python3
"""Restore Dockerfile path and redeploy after failed Dockerfile.deploy attempt."""

from __future__ import annotations

import json
import sys
import time
import urllib.request

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"


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
    name = app.get("appName", "homa-task-bot-qsnkoy")
    print("before:", app.get("applicationStatus"), "dockerfile=", app.get("dockerfile"))

    api("POST", "application.update", {
        "applicationId": APP,
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "buildType": "dockerfile",
        "sourceType": "drop",
        "dockerImage": f"{name}:latest",
        "cleanCache": False,
        "applicationStatus": "idle",
        "replicas": 1,
    })
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": "recover bot after failed deploy",
        "description": "restore_dockerfile.py",
    })
    print("waiting 90s ...")
    time.sleep(90)
    deps = api("GET", f"deployment.allByType?id={APP}&type=application")
    dep = deps[0]
    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = log if isinstance(log, str) else str(log)
    if text.startswith('"'):
        text = json.loads(text)
    print("deploy:", dep.get("status"))
    print(text[-1500:])
    app2 = api("GET", f"application.one?applicationId={APP}")
    print("after:", app2.get("applicationStatus"))
    return 0 if dep.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
