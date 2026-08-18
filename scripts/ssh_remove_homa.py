#!/usr/bin/env python3
"""Definitively remove the Homa swarm service (root cause of the meltdown).

Removing the container alone is futile: Swarm reschedules it. We must remove the
service. Then verify load drops and infra is healthy.
"""

from __future__ import annotations

import sys
import time

import paramiko

HOST = "217.114.40.67"
USER = "root"
PASSWORD = "onznbxc1BccO1Ys1"

CMD = r"""
set +e
echo "===== REMOVE HOMA SWARM SERVICE ====="
docker service ls --format '{{.Name}}' | grep -i homa | while read svc; do
  echo "removing service: $svc"
  docker service rm "$svc"
done
echo
echo "===== KILL ANY LEFTOVER HOMA CONTAINERS ====="
LEFT=$(docker ps -aq --filter name=homa)
if [ -n "$LEFT" ]; then docker rm -f $LEFT && echo "removed leftover: $LEFT"; else echo "none"; fi
echo
sleep 5
echo "===== SERVICES NOW ====="
docker service ls --format "{{.Name}}\t{{.Replicas}}"
echo
echo "===== HOMA CONTAINERS NOW (should be empty) ====="
docker ps -a --filter name=homa --format "{{.Names}}\t{{.Status}}"
echo
echo "===== TOP CPU ====="
ps -eo pid,pcpu,pmem,comm --sort=-pcpu | head -8
echo
echo "===== LOAD ====="
uptime
echo "REMOVE_DONE"
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
    _, stdout, stderr = client.exec_command(CMD, timeout=150)
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
