#!/usr/bin/env python3
"""Upload full project ZIP via application.dropDeployment (replaces stale drop)."""

from __future__ import annotations

import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"
ROOT = Path(__file__).resolve().parents[1]

SKIP_PARTS = {".venv", "__pycache__", ".git", "credentials", "scripts", "agent-tools"}


def collect_files() -> list[str]:
    names: set[str] = {
        "build_id.txt",
        "Dockerfile",
        "requirements.txt",
        "config.py",
        ".dockerignore",
        "vendor/sing-box",
    }
    for pattern in ("bot/**/*.py", "services/**/*.py"):
        for path in ROOT.glob(pattern):
            rel = path.relative_to(ROOT).as_posix()
            if any(part in SKIP_PARTS for part in path.parts):
                continue
            names.add(rel)
    return sorted(names)


def build_zip(files: list[str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in files:
            zf.write(ROOT / rel, rel)
    return buf.getvalue()


def api_json(method: str, path: str, data: dict | None = None) -> object:
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


try:
    import requests
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests


def upload_zip(zip_bytes: bytes) -> bool:
    """Upload via tRPC endpoint (OpenAPI path returns 500 on this server)."""
    url = f"{API}/trpc/application.dropDeployment"
    response = requests.post(
        url,
        headers={"x-api-key": KEY},
        files={"zip": ("homa-task.zip", zip_bytes, "application/zip")},
        data={"applicationId": APP},
        timeout=300,
    )
    print("upload status", response.status_code, response.text[:200])
    return response.status_code == 200 and "true" in response.text.lower()


def latest_dep() -> dict:
    items = api_json("GET", f"deployment.allByType?id={APP}&type=application")
    return items[0]  # type: ignore[index]


def dep_log(dep_id: str) -> str:
    result = api_json("GET", f"deployment.readLogs?deploymentId={dep_id}")
    if isinstance(result, str) and result.startswith('"'):
        return json.loads(result)
    return result if isinstance(result, str) else str(result)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build_id = (ROOT / "build_id.txt").read_text(encoding="utf-8").strip() or str(int(time.time()))
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )

    files = collect_files()
    zip_bytes = build_zip(files)
    print(f"build_id={build_id} zip_files={len(files)} zip_size={len(zip_bytes)}")

    for path, payload in [
        ("application.stop", {"applicationId": APP}),
        ("application.cleanQueues", {"applicationId": APP}),
        ("application.killBuild", {"applicationId": APP}),
    ]:
        try:
            api_json("POST", path, payload)
            print("ok", path)
        except Exception as exc:  # noqa: BLE001
            print("skip", path, exc)

    if not upload_zip(zip_bytes):
        print("ZIP upload failed")
        return 1

    app = api_json("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy") if isinstance(app, dict) else "homa-task-bot-qsnkoy"

    api_json("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "dockerImage": f"{app_name}:latest",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "applicationStatus": "idle",
    })

    print("redeploy after zip upload ...")
    api_json("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"ZIP drop deploy {build_id}",
        "description": "upload_zip_deploy.py",
    })

    dep: dict = {}
    for i in range(80):
        time.sleep(10)
        dep = latest_dep()
        status = dep.get("status", "?")
        print("poll", i + 1, status)
        if status in {"done", "error"}:
            break

    log = dep_log(dep.get("deploymentId", ""))
    build_ok = "grep -q" in log and "sheets_async" in log
    print("build_ok", build_ok)
    print(log[-5000:].encode("ascii", errors="replace").decode("ascii"))

    time.sleep(15)
    api_json("POST", "application.stop", {"applicationId": APP})
    time.sleep(5)
    api_json("POST", "application.start", {"applicationId": APP})
    time.sleep(25)

    rt = api_json("GET", f"application.readLogs?applicationId={APP}&tail=80")
    rt_text = json.loads(rt) if isinstance(rt, str) and rt.startswith('"') else (rt if isinstance(rt, str) else str(rt))
    runtime_ok = "Handlers loaded" in rt_text or "Sheets cache warmed" in rt_text
    print("runtime_ok", runtime_ok)
    print(rt_text[-2500:].encode("ascii", errors="replace").decode("ascii"))

    if dep.get("status") == "done" and (build_ok or runtime_ok):
        print("DEPLOY_OK")
        return 0
    print("DEPLOY_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
