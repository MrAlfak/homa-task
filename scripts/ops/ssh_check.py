#!/usr/bin/env python3
"""Verify recovery: what's still running, top CPU, load. Re-stop stragglers."""

from __future__ import annotations

import sys
import time

import paramiko

HOST = "217.114.40.67"
USER = "root"
PASSWORD = "onznbxc1BccO1Ys1"

CHECK = r"""
set +e
echo "===== LOAD ====="
uptime
echo
echo "===== RUNNING CONTAINERS ====="
docker ps --format "{{.Names}}\t{{.Status}}"
echo
echo "===== RE-STOP ANY APP STRAGGLERS (keep infra) ====="
KEEP='dokploy|traefik|postgres|redis|mariadb|mysql|mongo|database|-db'
APPS=$(docker ps --format '{{.ID}} {{.Names}}' | grep -Ev "$KEEP" | awk '{print $1}')
if [ -n "$APPS" ]; then docker stop $APPS && echo "stopped stragglers"; else echo "none running"; fi
echo
echo "===== TOP CPU PROCESSES (host) ====="
ps -eo pid,ppid,pcpu,pmem,comm --sort=-pcpu | head -15
echo
echo "===== MEMORY ====="
free -h
echo
echo "===== LOAD (final) ====="
uptime
echo "CHECK_DONE"
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[{time.strftime('%H:%M:%S')}] connect {USER}@{HOST} ...", flush=True)
    client.connect(
        HOST, port=22, username=USER, password=PASSWORD,
        timeout=30, banner_timeout=150, auth_timeout=120,
        look_for_keys=False, allow_agent=False,
    )
    tr = client.get_transport()
    if tr is not None:
        tr.set_keepalive(15)
    print("CONNECTED\n", flush=True)
    _, stdout, stderr = client.exec_command(CHECK, timeout=180)
    for line in iter(stdout.readline, ""):
        print(line.rstrip(), flush=True)
    err = stderr.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1500], flush=True)
    client.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SSH_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
