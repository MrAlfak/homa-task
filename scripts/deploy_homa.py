#!/usr/bin/env python3
"""Create + configure + deploy the Homa Task Bot in the Homa Dokploy project.

Source = locally built docker image (single-node swarm).
Hard resource caps + bounded restart policy so it can never melt the host again.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = "https://blob.firstdata.ir/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
ENV_ID = "McAY4r1-8icHcCTwRaNyN"   # Homa / production
ROOT = Path(__file__).resolve().parents[1]
ctx = ssl.create_default_context()


def call(path: str, data: dict, timeout: int = 120) -> dict:
    req = urllib.request.Request(
        f"{API}/{path}",
        data=json.dumps(data).encode(),
        method="POST",
        headers={"x-api-key": KEY, "Content-Type": "application/json", "Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            raw = r.read().decode()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code} on {path}: {body[:400]}") from exc


def build_env() -> str:
    creds = json.loads((ROOT / "credentials" / "google-service-account.json").read_text(encoding="utf-8"))
    creds_json = json.dumps(creds, separators=(",", ":"))
    token = ""
    for line in (ROOT / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("BOT_TOKEN="):
            token = line.split("=", 1)[1].strip()
    return (
        f"BOT_TOKEN={token}\n"
        "GOOGLE_SHEET_ID=1-JjUkuQm7D5pSHsm_ssrSw-u9588FJeYwzjJ4sli4Uk\n"
        f"GOOGLE_CREDENTIALS_JSON={creds_json}\n"
        "GOOGLE_CREDENTIALS_PATH=/tmp/google-service-account.json\n"
        "BOT_MODE=polling\n"
        "FATAL_RESTART_DELAY=20\n"
    )


def main() -> int:
    print("1) create application in Homa/production ...")
    created = call("application.create", {
        "name": "Homa Task Bot",
        "appName": "homa-task-bot",
        "description": "Telegram task management bot (optimized, no proxy)",
        "environmentId": ENV_ID,
    })
    app_id = created.get("applicationId") or created.get("data", {}).get("applicationId")
    if not app_id:
        print("create response:", json.dumps(created)[:400])
        raise RuntimeError("no applicationId returned")
    print("   applicationId:", app_id)

    print("2) configure docker source + resource caps + safe restart policy ...")
    call("application.update", {
        "applicationId": app_id,
        "sourceType": "docker",
        "dockerImage": "homa-task-bot:latest",
        "replicas": 1,
        "memoryLimit": "256m",
        "memoryReservation": "64m",
        "cpuLimit": "0.5",
        "cpuReservation": "0.1",
        "restartPolicySwarm": {
            "Condition": "on-failure",
            "Delay": 10_000_000_000,        # 10s (nanoseconds)
            "MaxAttempts": 5,
            "Window": 180_000_000_000,      # 180s (nanoseconds)
        },
    })
    print("   updated")

    print("3) save clean environment (no proxy) ...")
    call("application.saveEnvironment", {
        "applicationId": app_id,
        "env": build_env(),
        "buildArgs": None,
        "buildSecrets": None,
        "createEnvFile": True,
    }, timeout=180)
    print("   env saved")

    print("4) deploy ...")
    call("application.deploy", {
        "applicationId": app_id,
        "title": "Optimized bot, resource-capped (no VLESS)",
        "description": "256m / 0.5cpu, bounded restart policy",
    })
    print("DEPLOY_TRIGGERED", app_id)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"DEPLOY_ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
