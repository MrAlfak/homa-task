#!/usr/bin/env python3
"""Point Dokploy app at freshly built drop image (not stale registry tag)."""

from __future__ import annotations

import json
import sys
import time
import urllib.request

API_BASE = "http://217.114.40.67:3000/api"
API_KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP_ID = "yJuZ9FANN1ctYrbdtFa3W"


def api(method: str, path: str, data: dict | None = None) -> object:
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        data=body,
        method=method,
        headers={"x-api-key": API_KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    app = api("GET", f"application.one?applicationId={APP_ID}")
    if not isinstance(app, dict):
        print("unexpected app response")
        return 1

    app_name = app.get("appName", "homa-task-bot-qsnkoy")
    built_image = f"{app_name}:latest"
    print(f"current dockerImage: {app.get('dockerImage')}")
    print(f"target dockerImage:  {built_image}")

    api("POST", "application.update", {
        "applicationId": APP_ID,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "dockerImage": built_image,
        "cleanCache": True,
        "replicas": 1,
    })
    print("updated application")

    api("POST", "application.redeploy", {
        "applicationId": APP_ID,
        "title": "Use built drop image",
        "description": "fix_image_tag.py",
    })
    print("redeploy triggered, waiting 100s ...")
    time.sleep(100)

    logs = api("GET", f"application.readLogs?applicationId={APP_ID}&tail=120")
    text = logs if isinstance(logs, str) else str(logs)
    if text.startswith('"'):
        text = json.loads(text)
    for needle in ("Handlers loaded", "Running build", "build "):
        print(f"contains {needle!r}:", needle in text)
    print("\n--- tail ---")
    print(text[-3500:])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
