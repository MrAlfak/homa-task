#!/usr/bin/env python3
"""Upload bot source to the server over SFTP and build the Docker image.

Single-node swarm => a locally built image is usable directly by the service,
so no registry is required.
"""

from __future__ import annotations

import sys
from pathlib import Path

import paramiko

HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"
ROOT = Path(__file__).resolve().parents[1]
REMOTE = "/opt/homa-build"

FILES = [
    "Dockerfile",
    "requirements.txt",
    "config.py",
    "vendor/sing-box",
    "bot/__init__.py",
    "bot/runner.py",
    "bot/main.py",
    "bot/proxy.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/auth.py",
]

REMOTE_DIRS = ["", "bot", "bot/handlers", "services"]


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"connect {USER}@{HOST} ...", flush=True)
    c.connect(HOST, username=USER, password=PW, timeout=30, banner_timeout=120,
              auth_timeout=120, look_for_keys=False, allow_agent=False)

    # Fresh build dir
    _run(c, f"rm -rf {REMOTE} && mkdir -p {REMOTE}/bot/handlers {REMOTE}/services {REMOTE}/vendor")

    sftp = c.open_sftp()
    for rel in FILES:
        local = ROOT / rel
        remote = f"{REMOTE}/{rel}"
        sftp.put(str(local), remote)
        print(f"  uploaded {rel}", flush=True)
    sftp.close()

    print("\nbuilding image homa-task-bot:latest ...", flush=True)
    _run(c, f"cd {REMOTE} && docker build -t homa-task-bot:latest . 2>&1 | tail -n 30")
    _run(c, "docker images homa-task-bot:latest --format '{{.Repository}}:{{.Tag}} {{.ID}} {{.Size}}'")
    print("BUILD_DONE", flush=True)
    c.close()
    return 0


def _run(client: paramiko.SSHClient, cmd: str, timeout: int = 600) -> None:
    _, o, e = client.exec_command(cmd, timeout=timeout)
    for line in iter(o.readline, ""):
        print(line.rstrip(), flush=True)
    err = e.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:2000], flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"BUILD_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
