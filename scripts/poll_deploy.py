#!/usr/bin/env python3
"""Poll latest deployment and show build context size."""

from __future__ import annotations

import json
import sys
import urllib.request

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"


def api(path: str) -> object:
    req = urllib.request.Request(
        f"{API}/{path}",
        headers={"x-api-key": KEY, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        raw = r.read().decode()
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return raw


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    deps = api(f"deployment.allByType?id={APP}&type=application")
    for d in deps[:3]:
        log = api(f"deployment.readLogs?deploymentId={d['deploymentId']}")
        ctx = ""
        if isinstance(log, str):
            for line in log.splitlines():
                if "transferring context" in line:
                    ctx = line.strip()
        print(d["createdAt"][:19], d["status"], d["title"][:40])
        print(" ", ctx or "(no context line)")
        if isinstance(log, str) and "announce" in log.lower():
            print("  has announce in log")
    app = api(f"application.one?applicationId={APP}")
    data = app.get("data", app) if isinstance(app, dict) else app
    print("\napp:", data.get("applicationStatus"), "replicas:", data.get("replicas"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
