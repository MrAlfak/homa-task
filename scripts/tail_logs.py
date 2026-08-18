#!/usr/bin/env python3
"""Tail fresh logs from the current Homa container (filter proxy node spam)."""

from __future__ import annotations

import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"

CMD = r"""
set +e
CID=$(docker ps --filter name=homa-task-bot --format '{{.ID}}' | head -1)
echo "container: $CID"
[ -z "$CID" ] && exit 0
echo "===== bot logs (filtered) ====="
docker logs --tail 60 "$CID" 2>&1 | grep -Ev "Skipping node" | tail -40
echo
echo "===== socks port check ====="
docker exec "$CID" sh -c 'ss -ltn 2>/dev/null | grep 10808 || echo "no listener"'
echo TAIL_DONE
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30, banner_timeout=120,
              auth_timeout=120, look_for_keys=False, allow_agent=False)
    _, o, e = c.exec_command(CMD, timeout=60)
    print(o.read().decode(errors="replace"))
    err = e.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1000])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
