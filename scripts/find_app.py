#!/usr/bin/env python3
"""Locate the current Homa application id + key settings in Homa/production."""

from __future__ import annotations

import json
import ssl
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://blob.firstdata.ir/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
ctx = ssl.create_default_context()


def api_get(path: str):
    req = urllib.request.Request(f"{API}/{path}", headers={"x-api-key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode())


def main() -> None:
    projects = api_get("project.all")
    data = projects.get("data", projects) if isinstance(projects, dict) else projects
    for p in data:
        if "homa" not in (p.get("name", "").lower()):
            continue
        print("project:", p.get("name"), p.get("projectId"))
        for env in p.get("environments", []):
            print("  env:", env.get("name"), env.get("environmentId"))
            for app in env.get("applications", []) or []:
                print("    APP:", app.get("name"),
                      "| id:", app.get("applicationId"),
                      "| image:", app.get("dockerImage"),
                      "| src:", app.get("sourceType"),
                      "| replicas:", app.get("replicas"),
                      "| memLimit:", app.get("memoryLimit"),
                      "| status:", app.get("applicationStatus"))


if __name__ == "__main__":
    main()
