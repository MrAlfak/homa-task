#!/usr/bin/env python3
"""Verify the deployed Homa service: running state, resource limits, logs, load."""

from __future__ import annotations

import sys
import time

import paramiko

HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"

CMD = r"""
set +e
echo "===== HOMA SERVICE ====="
docker service ls --format '{{.Name}}\t{{.Mode}}\t{{.Replicas}}\t{{.Image}}' | grep -i homa || echo "NO HOMA SERVICE YET"
echo
SVC=$(docker service ls --format '{{.Name}}' | grep -i homa | head -1)
if [ -n "$SVC" ]; then
  echo "===== RESOURCE LIMITS ($SVC) ====="
  docker service inspect "$SVC" --format 'Limits: {{.Spec.TaskTemplate.Resources.Limits}} | Reservations: {{.Spec.TaskTemplate.Resources.Reservations}}'
  echo "Restart: {{ }}"
  docker service inspect "$SVC" --format 'RestartPolicy: {{.Spec.TaskTemplate.RestartPolicy}}'
  echo
  echo "===== TASK STATE ====="
  docker service ps "$SVC" --no-trunc --format '{{.Name}}\t{{.CurrentState}}\t{{.Error}}' | head -6
  echo
  echo "===== LAST LOGS ====="
  docker service logs "$SVC" --tail 25 2>&1 | tail -25
fi
echo
echo "===== LOAD / MEM ====="
uptime
free -h | head -2
echo "VERIFY_DONE"
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30, banner_timeout=120,
              auth_timeout=120, look_for_keys=False, allow_agent=False)
    _, o, e = c.exec_command(CMD, timeout=120)
    for line in iter(o.readline, ""):
        print(line.rstrip(), flush=True)
    err = e.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1500], flush=True)
    c.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"VERIFY_ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
