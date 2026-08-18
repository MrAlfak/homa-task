#!/usr/bin/env python3
"""Deploy build 1783607708, verify, then broadcast changelog to all Personnel."""

from __future__ import annotations

import asyncio
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"
BUILD_ID = "1783607708"


def collect_project_files() -> list[str]:
    names: set[str] = {
        "build_id.txt",
        "Dockerfile",
        "requirements.txt",
        "config.py",
        ".dockerignore",
    }
    for pattern in ("bot/**/*.py", "services/**/*.py"):
        for path in ROOT.glob(pattern):
            if path.is_file():
                names.add(path.relative_to(ROOT).as_posix())
    return sorted(names)


def api(method: str, path: str, data: dict | None = None, *, timeout: int = 180) -> object:
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}/{path}",
        data=body,
        method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else {}


def latest_dep() -> dict:
    return api("GET", f"deployment.allByType?id={APP}&type=application")[0]  # type: ignore[index]


def dep_log(dep_id: str) -> str:
    result = api("GET", f"deployment.readLogs?deploymentId={dep_id}")
    if isinstance(result, str) and result.startswith('"'):
        return json.loads(result)
    return result if isinstance(result, str) else str(result)


def sync_via_ssh(files: list[str]) -> bool:
    try:
        import paramiko
    except ImportError:
        return False

    app = api("GET", f"application.one?applicationId={APP}")
    token = app.get("refreshToken", "") if isinstance(app, dict) else ""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            "217.114.40.67",
            username="root",
            password="onznbxc1BccO1Ys1",
            timeout=30,
            banner_timeout=120,
            auth_timeout=120,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:
        print(f"SSH connect failed: {exc}")
        return False

    drop = None
    for needle in (token, APP):
        cmd = (
            f"find /etc/dokploy /var/lib/dokploy -maxdepth 12 "
            f"-type d -name '{needle}' 2>/dev/null | head -1"
        )
        _, stdout, _ = client.exec_command(cmd, timeout=60)
        path = stdout.read().decode().strip()
        if path:
            drop = path
            break
    if not drop:
        client.close()
        return False

    print(f"SSH drop: {drop}")
    sftp = client.open_sftp()

    def ensure_parent(remote_path: str) -> None:
        parent = "/".join(remote_path.split("/")[:-1])
        cur = ""
        for part in parent.split("/"):
            if not part:
                continue
            cur = f"{cur}/{part}" if cur else part
            if not cur.startswith("/"):
                continue
            try:
                sftp.stat(cur)
            except OSError:
                try:
                    sftp.mkdir(cur)
                except OSError:
                    pass

    for rel in files:
        dst = f"{drop}/{rel}"
        ensure_parent(dst)
        sftp.put(str(ROOT / rel), dst)
        print(f"  put {rel}")
    sftp.close()
    client.close()
    return True


def deploy() -> tuple[dict, str]:
    for path, payload in [
        ("application.cleanQueues", {"applicationId": APP}),
        ("application.killBuild", {"applicationId": APP}),
    ]:
        try:
            api("POST", path, payload)
        except Exception:
            pass

    app = api("GET", f"application.one?applicationId={APP}")
    app_name = app.get("appName", "homa-task-bot-qsnkoy") if isinstance(app, dict) else "homa-task-bot-qsnkoy"

    api("POST", "application.update", {
        "applicationId": APP,
        "sourceType": "drop",
        "buildType": "dockerfile",
        "dockerfile": "Dockerfile",
        "dockerContextPath": ".",
        "dockerImage": f"{app_name}:latest",
        "cleanCache": False,
        "buildArgs": f"APP_BUILD_ID={BUILD_ID}",
        "applicationStatus": "idle",
        "replicas": 1,
    })
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"Fix /start task flow {BUILD_ID}",
        "description": "deploy_release.py",
    })

    dep: dict = {}
    for i in range(50):
        time.sleep(10)
        dep = latest_dep()
        status = dep.get("status", "?")
        print(f"poll {i + 1}: {status}")
        if status in {"done", "error"}:
            break
    return dep, dep_log(dep.get("deploymentId", ""))


async def broadcast() -> int:
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    from bot.messages.changelog import build_changelog_announcement
    from bot.proxy import start_proxy
    from config import config
    from services.sheets import get_sheets_service

    recipients = get_sheets_service().get_broadcast_recipients()
    if not recipients:
        print("No broadcast recipients.")
        return 1

    proxy_url = start_proxy()
    session = None
    if proxy_url:
        from aiogram.client.session.aiohttp import AiohttpSession

        session = AiohttpSession(proxy=proxy_url)

    bot = Bot(
        token=config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        session=session,
    )
    sent = failed = 0
    try:
        me = await bot.get_me()
        body = build_changelog_announcement(bot_name=me.full_name)
        for person in recipients:
            try:
                await bot.send_message(person.telegram_id, body, parse_mode="HTML")
                sent += 1
                print(f"OK  {person.name}")
                await asyncio.sleep(0.08)
            except Exception as exc:
                failed += 1
                print(f"ERR {person.name}: {exc}")
    finally:
        await bot.session.close()

    print(f"Broadcast: sent={sent} failed={failed} total={len(recipients)}")
    return 0 if failed == 0 else 2


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    files = collect_project_files()
    print(f"build_id={BUILD_ID} files={len(files)}")

    if not sync_via_ssh(files):
        print("SSH sync failed, using patch API...")
        for rel in files:
            api("POST", "patch.saveFileAsPatch", {
                "id": APP,
                "type": "application",
                "filePath": rel,
                "content": (ROOT / rel).read_text(encoding="utf-8"),
                "patchType": "update",
            })
        app_name = api("GET", f"application.one?applicationId={APP}")
        name = app_name.get("appName", "homa-task-bot-qsnkoy") if isinstance(app_name, dict) else "homa-task-bot-qsnkoy"
        for i in range(5):
            api("POST", "application.reload", {"applicationId": APP, "appName": name})
            time.sleep(10)

    dep, log = deploy()
    print(log[-5000:])
    build_ok = "grep -q" in log and "sheets_async" in log and dep.get("status") == "done"
    print(f"deploy status={dep.get('status')} build_ok={build_ok}")

    if not build_ok:
        print("DEPLOY_FAILED — skipping broadcast")
        return 1

    time.sleep(20)
    api("POST", "application.start", {"applicationId": APP})
    time.sleep(15)
    return asyncio.run(broadcast())


if __name__ == "__main__":
    raise SystemExit(main())
