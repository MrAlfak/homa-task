#!/usr/bin/env python3
"""Exec into the running Homa container to find out WHY sing-box exits."""

from __future__ import annotations

import sys

import paramiko

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"

CMD = r"""
set +e
CID=$(docker ps --filter "name=homa-task-bot" --format '{{.ID}}' | head -1)
echo "container: $CID"
[ -z "$CID" ] && { echo "NO CONTAINER"; exit 0; }
echo "===== sing-box version ====="
docker exec "$CID" /usr/local/bin/sing-box version 2>&1 | head -3
echo
echo "===== config check ====="
docker exec "$CID" /usr/local/bin/sing-box check -c /tmp/sing-box.json 2>&1 | head -30
echo
echo "===== run 5s (stderr) ====="
docker exec "$CID" timeout 5 /usr/local/bin/sing-box run -c /tmp/sing-box.json 2>&1 | head -40
echo
echo "===== config head ====="
docker exec "$CID" head -c 1200 /tmp/sing-box.json
echo
echo DIAG_DONE
"""


def main() -> int:
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30, banner_timeout=120,
              auth_timeout=120, look_for_keys=False, allow_agent=False)
    _, o, e = c.exec_command(CMD, timeout=90)
    print(o.read().decode(errors="replace"))
    err = e.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1500])
    c.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
