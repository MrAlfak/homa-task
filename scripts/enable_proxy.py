#!/usr/bin/env python3
"""Enable the embedded VLESS proxy on the existing Homa app and bring it online.

Safe by construction:
- Reuses the already-pushed local-registry image (resilient runner + bounded
  restart policy already configured server-side).
- Merges proxy env vars into the CURRENT env (never wipes existing secrets).
- Bumps memory to 384 MiB to give sing-box headroom; keeps CPU cap at 0.5.
"""

from __future__ import annotations

import json
import ssl
import sys
import urllib.error
import urllib.request

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

API = "https://blob.firstdata.ir/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP_ID = "yJuZ9FANN1ctYrbdtFa3W"
SUB_URL = "https://sub.darklink.ir/sub/djMsMTYzNywxNzg0OTIxNTk2.edvjdgjpeUnD6q0DeWrC42110nhWycNsLdmAoA-8yQ8"
PROXY_PORT = "10808"
MEM_384 = str(384 * 1024 * 1024)  # 402653184 bytes
ctx = ssl.create_default_context()


def get(path: str) -> dict:
    req = urllib.request.Request(f"{API}/{path}", headers={"x-api-key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode())


def post(path: str, data: dict, timeout: int = 180) -> dict:
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


def merge_env(current: str) -> str:
    lines = [ln for ln in (current or "").splitlines() if ln.strip()]
    keys = {ln.split("=", 1)[0] for ln in lines if "=" in ln}
    additions = {
        "PROXY_ENABLED": "true",
        "VLESS_SUBSCRIPTION_URL": SUB_URL,
        "PROXY_PORT": PROXY_PORT,
    }
    for k, v in additions.items():
        if k in keys:
            lines = [(f"{k}={v}" if ln.split("=", 1)[0] == k else ln) for ln in lines]
        else:
            lines.append(f"{k}={v}")
    return "\n".join(lines) + "\n"


def main() -> int:
    print("1) read current app config/env ...")
    app = get(f"application.one?applicationId={APP_ID}")
    app = app.get("data", app)
    env = merge_env(app.get("env") or "")
    print("   env keys:", [ln.split("=", 1)[0] for ln in env.splitlines()])

    print("2) update resources: replicas=1, mem=384MiB, cpu=0.5 (policy unchanged) ...")
    post("application.update", {
        "applicationId": APP_ID,
        "replicas": 1,
        "memoryLimit": MEM_384,
        "memoryReservation": str(96 * 1024 * 1024),  # 96 MiB
        "cpuLimit": "500000000",
        "cpuReservation": "100000000",
        "restartPolicySwarm": {
            "Condition": "on-failure",
            "Delay": 10_000_000_000,
            "MaxAttempts": 5,
            "Window": 180_000_000_000,
        },
    })
    print("   updated")

    print("3) save merged environment (proxy enabled) ...")
    post("application.saveEnvironment", {
        "applicationId": APP_ID,
        "env": env,
        "buildArgs": None,
        "buildSecrets": None,
        "createEnvFile": True,
    })
    print("   env saved")

    print("4) deploy ...")
    post("application.deploy", {
        "applicationId": APP_ID,
        "title": "Enable embedded VLESS proxy (Reality nodes, urltest failover)",
        "description": "384MiB / 0.5cpu, bounded restart policy, sing-box supervised in-process",
    })
    print("DEPLOY_TRIGGERED", APP_ID)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:  # noqa: BLE001
        print(f"ENABLE_ERROR: {exc}", file=sys.stderr, flush=True)
        raise SystemExit(1) from exc
