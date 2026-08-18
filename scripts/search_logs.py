#!/usr/bin/env python3
"""Search Dokploy application logs for keywords."""

from __future__ import annotations

import json
import sys
import urllib.request

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    req = urllib.request.Request(
        f"{API}/application.readLogs?applicationId={APP}&tail=800",
        headers={"x-api-key": KEY},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        text = resp.read().decode()
    if text.startswith('"'):
        text = json.loads(text)

    needles = [
        "not handled",
        "announce",
        "employee_tasks loaded",
        "Handlers loaded",
        "grep -q",
    ]
    print(f"LOG LENGTH: {len(text)}")
    for n in needles:
        print(f"  {n!r}: {text.lower().count(n.lower())}")

    print("\n--- matching lines ---")
    for line in text.split("\n"):
        ll = line.lower()
        if any(n in ll for n in ("not handled", "announce", "employee_tasks loaded", "handlers loaded")):
            print(line[:400])

    deps_req = urllib.request.Request(
        f"{API}/deployment.allByType?id={APP}&type=application",
        headers={"x-api-key": KEY},
    )
    with urllib.request.urlopen(deps_req, timeout=60) as resp:
        deps = json.loads(resp.read().decode())
    dep = deps[0]
    print(f"\nLatest deploy: {dep.get('status')} id={dep.get('deploymentId')}")
    log_req = urllib.request.Request(
        f"{API}/deployment.readLogs?deploymentId={dep['deploymentId']}",
        headers={"x-api-key": KEY},
    )
    with urllib.request.urlopen(log_req, timeout=60) as resp:
        blog = resp.read().decode()
    if isinstance(blog, str) and blog.startswith('"'):
        blog = json.loads(blog)
    print("BUILD tail (last 2500 chars):")
    print(blog[-2500:] if len(blog) > 2500 else blog)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
