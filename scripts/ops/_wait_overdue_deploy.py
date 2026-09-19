#!/usr/bin/env python3
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"


def api(method: str, path: str, data: dict | None = None):
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(
        f"{API}/{path}",
        data=body,
        method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=120) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    dep: dict = {}
    for i in range(30):
        items = api("GET", f"deployment.allByType?id={APP}&type=application")
        dep = items[0]
        status = dep.get("status")
        print("poll", i + 1, status, dep.get("title"))
        if status in {"done", "error"}:
            break
        time.sleep(10)

    try:
        api("POST", "application.start", {"applicationId": APP})
        print("start ok")
    except Exception as exc:
        print("start", exc)

    time.sleep(35)
    logs = api("GET", f"application.readLogs?applicationId={APP}&tail=100")
    text = logs if isinstance(logs, str) else str(logs)
    if text.startswith('"'):
        text = json.loads(text)
    for line in text.split("\n"):
        if any(
            x in line
            for x in (
                "Overdue",
                "Handlers",
                "Connected",
                "Running build",
                "supervisor",
                "Error",
                "Traceback",
            )
        ):
            print(line)
    print("FINAL", dep.get("status"))
    return 0 if dep.get("status") == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
