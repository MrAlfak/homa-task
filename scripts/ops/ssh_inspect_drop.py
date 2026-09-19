#!/usr/bin/env python3
"""Inspect Dokploy drop/patch paths and homa service on server."""

from __future__ import annotations

import sys

import paramiko

HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"
TOKEN = "r0wGrAL7DmywMzVSp1vvu"

CMD = f"""
set +e
echo '=== FIND DROP PATH ==='
find /etc/dokploy -maxdepth 6 -type d -name '{TOKEN}' 2>/dev/null
find /var/lib/dokploy -maxdepth 6 -type d -name '{TOKEN}' 2>/dev/null

echo '=== DROP CONTENTS (if any) ==='
for d in $(find /etc/dokploy /var/lib/dokploy -maxdepth 6 -type d -name '{TOKEN}' 2>/dev/null); do
  echo "-- $d"
  ls -la "$d" | head -20
  du -sh "$d" 2>/dev/null
done

echo '=== PATCH GIT REPOS ==='
find /etc/dokploy -maxdepth 8 -type d -name .git 2>/dev/null | grep -i patch | head -10

echo '=== DOKPLOY CONTAINER LOGS (deploy errors) ==='
docker logs dokploy.1.$(docker service ps dokploy -q --no-trunc 2>/dev/null | head -1) 2>&1 | tail -40

echo '=== HOMA SERVICE ==='
docker service ls --format '{{{{.Name}}}}\\t{{{{.Replicas}}}}\\t{{{{.Image}}}}' | grep -i homa || true
SVC=$(docker service ls --format '{{{{.Name}}}}' | grep homa-task | head -1)
echo "service=$SVC"
if [ -n "$SVC" ]; then
  docker service ps "$SVC" --no-trunc --format '{{{{.Name}}}}\\t{{{{.CurrentState}}}}\\t{{{{.Error}}}}' | head -5
  docker service logs "$SVC" --tail 20 2>&1 | tail -20
fi
echo INSPECT_DONE
"""


def main() -> int:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
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
    _, stdout, stderr = client.exec_command(CMD, timeout=120)
    for line in iter(stdout.readline, ""):
        print(line.rstrip(), flush=True)
    err = stderr.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:2000], flush=True)
    client.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
