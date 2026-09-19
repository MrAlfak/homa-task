#!/usr/bin/env python3
"""SSH into the Dokploy host and run emergency recovery.

Kills the crash-looping Homa VLESS bot, stops all *app* containers while
keeping infrastructure (dokploy/traefik/db), so the panel comes back.
"""

from __future__ import annotations

import sys
import time

import paramiko

HOST = "217.114.40.67"
USER = "root"
PASSWORD = "onznbxc1BccO1Ys1"

RECOVERY = r"""
set +e
echo "===== LOAD (before) ====="
uptime
echo
echo "===== TOP CONTAINERS BY CPU ====="
docker stats --no-stream --format "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}" | sort -t"$(printf '\t')" -k2 -hr | head -25
echo
echo "===== KILL HOMA BOT (root cause) ====="
HOMA=$(docker ps -aq --filter name=homa-task-bot)
if [ -n "$HOMA" ]; then docker rm -f $HOMA && echo "removed: $HOMA"; else echo "no homa container"; fi
echo
echo "===== STOP ALL APP CONTAINERS (keep infra) ====="
KEEP='dokploy|traefik|postgres|redis|mariadb|mysql|mongo|database|-db'
echo "will stop:"; docker ps --format '{{.Names}}' | grep -Ev "$KEEP"
APPS=$(docker ps --format '{{.ID}} {{.Names}}' | grep -Ev "$KEEP" | awk '{print $1}')
if [ -n "$APPS" ]; then docker stop $APPS; else echo "nothing to stop"; fi
echo
echo "===== INFRA STATUS ====="
docker ps --filter name=dokploy --format "{{.Names}}\t{{.Status}}"
docker ps --filter name=traefik --format "{{.Names}}\t{{.Status}}"
echo
echo "===== LOAD (after) ====="
uptime
echo "RECOVERY_DONE"
"""


def run(client: paramiko.SSHClient, cmd: str, timeout: int = 120) -> None:
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    for line in iter(stdout.readline, ""):
        print(line.rstrip(), flush=True)
    err = stderr.read().decode(errors="replace").strip()
    if err:
        print("[stderr]", err[:1000], flush=True)


def connect_with_retry(attempts: int = 60) -> paramiko.SSHClient:
    last = None
    for i in range(1, attempts + 1):
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        try:
            print(f"[{time.strftime('%H:%M:%S')}] connect attempt {i}/{attempts} ...", flush=True)
            client.connect(
                HOST,
                port=22,
                username=USER,
                password=PASSWORD,
                timeout=15,
                banner_timeout=60,
                auth_timeout=60,
                look_for_keys=False,
                allow_agent=False,
            )
            tr = client.get_transport()
            if tr is not None:
                tr.set_keepalive(15)
            print("CONNECTED", flush=True)
            return client
        except Exception as exc:  # noqa: BLE001
            last = exc
            print(f"   fail: {type(exc).__name__}: {exc}", flush=True)
            try:
                client.close()
            except Exception:
                pass
            time.sleep(2)
    raise RuntimeError(f"could not connect after {attempts} attempts: {last}")


def main() -> int:
    client = connect_with_retry()
    print("Running recovery...\n", flush=True)
    run(client, RECOVERY, timeout=180)
    client.close()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"SSH_ERROR: {type(exc).__name__}: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
