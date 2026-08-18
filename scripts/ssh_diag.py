#!/usr/bin/env python3
"""Identify heavy process and which docker service it belongs to; list swarm services."""

from __future__ import annotations

import sys
import time

import paramiko

HOST = "217.114.40.67"
USER = "root"
PASSWORD = "onznbxc1BccO1Ys1"

CMD = r"""
set +e
echo "===== LOAD ====="
uptime
echo
echo "===== TOP CPU (host) ====="
ps -eo pid,pcpu,pmem,comm,args --sort=-pcpu | head -8
echo
echo "===== DOCKER STATS ====="
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | sort -t"$(printf '\t')" -k2 -hr | head -15
echo
echo "===== SWARM SERVICES ====="
docker service ls --format "{{.Name}}\t{{.Mode}}\t{{.Replicas}}"
echo "CMD_DONE"
"""


def main() -> int:
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    print(f"[{time.strftime('%H:%M:%S')}] connect {USER}@{HOST} ...", flush=True)
    client.connect(
        HOST, port=22, username=USER, password=PASSWORD,
        timeout=30, banner_timeout=120, auth_timeout=120,
        look_for_keys=False, allow_agent=False,
    )
    print("CONNECTED\n", flush=True)
    _, stdout, stderr = client.exec_command(CMD, timeout=120)
    for line in iter(stdout.readline, ""):
        print(line.rstrip(), flush=True)
    err = stderr.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1200], flush=True)
    client.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SSH_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
