#!/usr/bin/env python3
"""Try application.deploy (patch apply path) instead of redeploy."""

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


def collect_files() -> list[str]:
    names = {"build_id.txt", "Dockerfile", "requirements.txt", "config.py", ".dockerignore"}
    for pattern in ("bot/**/*.py", "services/**/*.py"):
        for path in ROOT.glob(pattern):
            names.add(path.relative_to(ROOT).as_posix())
    return sorted(names)


def api(method: str, path: str, data: dict | None = None) -> object:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}/{path}", data=body, method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n")
    (ROOT / "bot" / "__init__.py").write_text(f'"""Bot package."""\n__build__ = "{build_id}"\n')

    api("POST", "application.cleanQueues", {"applicationId": APP})
    api("POST", "application.killBuild", {"applicationId": APP})
    api("POST", "application.refreshToken", {"applicationId": APP})
    api("POST", "patch.ensureRepo", {"id": APP, "type": "application"})

    for rel in collect_files():
        api("POST", "patch.saveFileAsPatch", {
            "id": APP, "type": "application", "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": "update",
        })

    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")

    for i in range(10):
        api("POST", "application.reload", {"applicationId": APP, "appName": app_name})
        print("reload", i + 1)
        time.sleep(10)

    api("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "dockerImage": f"{app_name}:latest",
    })

    print("application.deploy ...")
    api("POST", "application.deploy", {
        "applicationId": APP,
        "title": f"Patch deploy {build_id}",
        "description": "deploy_apply.py",
    })

    dep = {}
    for i in range(40):
        time.sleep(5)
        dep = api("GET", f"deployment.allByType?id={APP}&type=application")[0]
        print("poll", i + 1, dep.get("status"))
        if dep.get("status") in ("done", "error"):
            break

    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = json.loads(log) if isinstance(log, str) and log.startswith('"') else (log if isinstance(log, str) else str(log))
    print("COPY build_id", "COPY build_id" in text)
    print("grep sheets_async", "sheets_async" in text and "grep" in text)
    print("Applying", "Applying" in text)
    print(text[-4000:].encode("ascii", errors="replace").decode("ascii"))

    time.sleep(20)
    rt = api("GET", f"application.readLogs?applicationId={APP}&tail=50")
    rt_text = json.loads(rt) if isinstance(rt, str) and rt.startswith('"') else (rt if isinstance(rt, str) else str(rt))
    print("Handlers loaded", "Handlers loaded" in rt_text)
    return 0 if dep.get("status") == "done" and "Handlers loaded" in rt_text else 1


if __name__ == "__main__":
    raise SystemExit(main())
