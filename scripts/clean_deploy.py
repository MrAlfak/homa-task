#!/usr/bin/env python3
"""Clean slate: wipe queues, refresh drop, sync all files, redeploy, verify."""

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

SSH_HOST, SSH_USER, SSH_PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"


def collect_project_files() -> list[str]:
    """All runtime source files to ship to Dokploy."""
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


def unwrap(app: object) -> dict:
    if isinstance(app, dict) and "data" in app:
        return app["data"]  # type: ignore[return-value]
    return app  # type: ignore[return-value]


def latest_dep() -> dict:
    items = api("GET", f"deployment.allByType?id={APP}&type=application")
    return items[0]  # type: ignore[index]


def dep_log(dep_id: str) -> str:
    result = api("GET", f"deployment.readLogs?deploymentId={dep_id}")
    if isinstance(result, str) and result.startswith('"'):
        return json.loads(result)
    return result if isinstance(result, str) else str(result)


def runtime_log(tail: int = 80) -> str:
    result = api("GET", f"application.readLogs?applicationId={APP}&tail={tail}")
    if isinstance(result, str) and result.startswith('"'):
        return json.loads(result)
    return result if isinstance(result, str) else str(result)


def clean_dokploy() -> dict:
    print("=== 1) Clean Dokploy state ===")
    for path, payload in [
        ("application.stop", {"applicationId": APP}),
        ("application.cleanQueues", {"applicationId": APP}),
        ("application.killBuild", {"applicationId": APP}),
    ]:
        try:
            api("POST", path, payload)
            print(f"   ok {path}")
        except Exception as exc:  # noqa: BLE001
            print(f"   skip {path}: {exc}")

    try:
        api("POST", "patch.cleanPatchRepos", {})
        print("   ok patch.cleanPatchRepos")
    except Exception as exc:  # noqa: BLE001
        print(f"   skip patch.cleanPatchRepos: {exc}")

    api("POST", "application.refreshToken", {"applicationId": APP})
    app = unwrap(api("GET", f"application.one?applicationId={APP}"))
    print(f"   new refreshToken: {app.get('refreshToken')}")
    api("POST", "patch.ensureRepo", {"id": APP, "type": "application"})
    return app


def sync_via_ssh(app: dict, files: list[str]) -> bool:
    print("\n=== 2) SSH sync into drop directory ===")
    try:
        import paramiko
    except ImportError:
        print("   paramiko not installed — skip SSH")
        return False

    token = app.get("refreshToken", "")
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            SSH_HOST,
            username=SSH_USER,
            password=SSH_PW,
            timeout=30,
            banner_timeout=120,
            auth_timeout=120,
            look_for_keys=False,
            allow_agent=False,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"   SSH connect failed: {exc}")
        return False

    def find_drop() -> str | None:
        for needle in (token, APP):
            cmd = (
                f"find /etc/dokploy /var/lib/dokploy -maxdepth 12 "
                f"-type d -name '{needle}' 2>/dev/null | head -1"
            )
            _, stdout, _ = client.exec_command(cmd, timeout=60)
            path = stdout.read().decode().strip()
            if path:
                return path
        return None

    drop = find_drop()
    if not drop:
        print("   drop directory not found")
        client.close()
        return False

    print(f"   drop: {drop}")
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
        src = ROOT / rel
        dst = f"{drop}/{rel}"
        ensure_parent(dst)
        sftp.put(str(src), dst)
        print(f"   put {rel}")

    sftp.close()
    _, stdout, _ = client.exec_command(
        f"grep -c 'sheets_async' {drop}/bot/main.py 2>/dev/null || echo 0",
        timeout=30,
    )
    print("   verify main.py sheets_async:", stdout.read().decode().strip())
    _, stdout, _ = client.exec_command(
        f"grep -c 'GENERAL_PROJECT_CATEGORIES' {drop}/services/sheets.py 2>/dev/null || echo 0",
        timeout=30,
    )
    print("   verify sheets general projects:", stdout.read().decode().strip())
    client.close()
    return True


def sync_via_patch_api(files: list[str]) -> None:
    print("\n=== 2b) Patch API upload (fallback) ===")
    for rel in files:
        patch_type = "create" if rel == "Dockerfile" else "update"
        api("POST", "patch.saveFileAsPatch", {
            "id": APP,
            "type": "application",
            "filePath": rel,
            "content": (ROOT / rel).read_text(encoding="utf-8"),
            "patchType": patch_type,
        })
        print(f"   {rel} ({patch_type})")

    app_name = unwrap(api("GET", f"application.one?applicationId={APP}")).get(
        "appName", "homa-task-bot-qsnkoy"
    )
    for i in range(8):
        api("POST", "application.reload", {"applicationId": APP, "appName": app_name})
        print(f"   reload {i + 1}/8")
        time.sleep(12)


def deploy(build_id: str, app_name: str) -> tuple[dict, str]:
    print("\n=== 3) Build & deploy ===")
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
    api("POST", "application.redeploy", {
        "applicationId": APP,
        "title": f"Clean deploy {build_id}",
        "description": "clean_deploy.py",
    })

    dep: dict = {}
    for i in range(40):
        time.sleep(5)
        dep = latest_dep()
        status = dep.get("status", "?")
        print(f"   poll {i + 1}: {status}")
        if status in {"done", "error"}:
            break
    return dep, dep_log(dep.get("deploymentId", ""))


def verify(build_log: str, runtime: str) -> bool:
    build_ok = "grep -q" in build_log and "sheets_async" in build_log
    runtime_ok = "Handlers loaded" in runtime or "Sheets cache warmed" in runtime
    print("\n=== 4) Verify ===")
    print(f"   build guard (sheets_async): {build_ok}")
    print(f"   runtime new code: {runtime_ok}")
    return build_ok and dep_status_ok(build_log)


def dep_status_ok(_: str) -> bool:
    return latest_dep().get("status") == "done"


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    build_id = str(int(time.time()))
    (ROOT / "build_id.txt").write_text(build_id + "\n", encoding="utf-8")
    (ROOT / "bot" / "__init__.py").write_text(
        f'"""Bot package."""\n__build__ = "{build_id}"\n',
        encoding="utf-8",
    )
    print(f"build_id={build_id}")

    files = collect_project_files()
    print(f"files to sync: {len(files)}")

    app = clean_dokploy()
    app_name = app.get("appName", "homa-task-bot-qsnkoy")

    if not sync_via_ssh(app, files):
        sync_via_patch_api(files)

    dep, log = deploy(build_id, app_name)
    safe_log = log[-6000:].encode("ascii", errors="replace").decode("ascii")
    print("\n--- BUILD LOG (tail) ---")
    print(safe_log)

    time.sleep(20)
    rt = runtime_log(100)
    safe_rt = rt[-3000:].encode("ascii", errors="replace").decode("ascii")
    print("\n--- RUNTIME LOG (tail) ---")
    print(safe_rt)

    build_ok = "grep -q" in log and "sheets_async" in log
    runtime_ok = "Handlers loaded" in rt or "Sheets cache warmed" in rt
    status = dep.get("status", "?")

    print(f"\nstatus={status} build_ok={build_ok} runtime_ok={runtime_ok}")

    if status == "done" and (build_ok or runtime_ok):
        print("DEPLOY_OK")
        return 0

    print("DEPLOY_FAILED")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
