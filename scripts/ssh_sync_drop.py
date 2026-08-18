#!/usr/bin/env python3
"""Sync local project files into Dokploy drop directory via SSH, then rebuild."""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import paramiko

HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"
APP = "yJuZ9FANN1ctYrbdtFa3W"
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
ROOT = Path(__file__).resolve().parents[1]

SYNC_FILES = [
    "build_id.txt",
    "Dockerfile",
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "bot/__init__.py",
    "bot/runner.py",
    "bot/main.py",
    "bot/proxy.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/announce.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "bot/messages/__init__.py",
    "bot/messages/changelog.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/auth.py",
]


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


def find_drop_dir(client: paramiko.SSHClient, token: str) -> str | None:
    cmd = (
        f"find /etc/dokploy /var/lib/dokploy -maxdepth 8 -type d -name '{token}' 2>/dev/null | head -1"
    )
    _, stdout, _ = client.exec_command(cmd, timeout=60)
    path = stdout.read().decode().strip()
    return path or None


def sftp_put_tree(sftp: paramiko.SFTPClient, local: Path, remote: str) -> None:
    for rel in SYNC_FILES:
        src = local / rel
        dst = f"{remote}/{rel.replace(chr(92), '/')}"
        parent = "/".join(dst.split("/")[:-1])
        parts = parent.split("/")
        cur = ""
        for part in parts:
            if not part:
                continue
            cur = f"{cur}/{part}" if cur else part
            if cur.startswith("/"):
                try:
                    sftp.stat(cur)
                except OSError:
                    try:
                        sftp.mkdir(cur)
                    except OSError:
                        pass
        sftp.put(str(src), dst)
        print("  put", rel)


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n", encoding="utf-8")
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )

    app = api("GET", f"application.one?applicationId={APP}")
    token = app.get("refreshToken", "")
    app_name = app.get("appName", "homa-task-bot-qsnkoy")
    print("refreshToken:", token)

    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        HOST,
        username=USER,
        password=PW,
        timeout=30,
        banner_timeout=120,
        auth_timeout=120,
        look_for_keys=False,
        allow_agent=False,
    )

    drop = find_drop_dir(client, token)
    if not drop:
        # Search by app id
        cmd = f"find /etc/dokploy /var/lib/dokploy -maxdepth 10 -type d -name '{APP}' 2>/dev/null | head -3"
        _, stdout, _ = client.exec_command(cmd, timeout=60)
        alt = stdout.read().decode().strip().split("\n")
        print("alt paths:", alt)
        drop = alt[0] if alt and alt[0] else None

    if not drop:
        print("ERROR: drop directory not found")
        client.close()
        return 1

    print("drop dir:", drop)
    sftp = client.open_sftp()
    sftp_put_tree(sftp, ROOT, drop)
    sftp.close()

    # Verify Dockerfile on server
    _, stdout, _ = client.exec_command(f"grep -c 'includes /announce handlers' {drop}/bot/handlers/employee_tasks.py", timeout=30)
    print("announce guard in drop:", stdout.read().decode().strip())
    _, stdout, _ = client.exec_command(f"grep -c 'build_id.txt' {drop}/Dockerfile", timeout=30)
    print("new Dockerfile in drop:", stdout.read().decode().strip())
    client.close()

    api("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "dockerImage": f"{app_name}:latest",
        "cleanCache": True,
        "buildArgs": f"APP_BUILD_ID={build_id}",
        "applicationStatus": "idle",
        "replicas": 1,
    })
    print("redeploy ...")
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"SSH drop sync {build_id}",
        "description": "ssh_sync_drop.py",
    })
    time.sleep(100)
    deps = api("GET", f"deployment.allByType?id={APP}&type=application")
    dep = deps[0]
    log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
    text = log if isinstance(log, str) else str(log)
    if text.startswith('"'):
        text = json.loads(text)
    print(text[-3500:])
    ok = "grep -q" in text and dep.get("status") == "done"
    print("BUILD_OK=", ok, "status=", dep.get("status"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
