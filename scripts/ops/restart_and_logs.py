#!/usr/bin/env python3
"""Restart Dokploy app and print recent logs."""

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
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
        if not raw:
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    print("stop...")
    api("POST", "application.stop", {"applicationId": APP_ID})
    time.sleep(5)
    print("start...")
    api("POST", "application.start", {"applicationId": APP_ID})
    time.sleep(30)
    result = api("GET", f"application.readLogs?applicationId={APP_ID}&tail=100")
    text = result if isinstance(result, str) else str(result)
    if text.startswith('"'):
        text = json.loads(text)
    for needle in ("Handlers loaded", "Running build", "Announce handler", "not handled", "announce"):
        print(f"\n--- contains '{needle}':", needle.lower() in text.lower())
    print("\n--- LOG TAIL ---")
    print(text[-5000:] if len(text) > 5000 else text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
