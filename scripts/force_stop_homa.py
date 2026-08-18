#!/usr/bin/env python3
"""Delete the Homa Task Bot from Dokploy (stops crash loop + removes app).

Host accepts TCP on 443 but TLS handshake stalls under CPU saturation, so we
retry until one request lands.
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.request

API_BASE = "https://blob.firstdata.ir/api"
API_KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP_ID = "ZTVQekZHYAAgnDEQD90mT"

ctx = ssl.create_default_context()


def call(path: str, data: dict, timeout: float) -> tuple[bool, str]:
    body = json.dumps(data).encode()
    req = urllib.request.Request(
        f"{API_BASE}/{path}",
        data=body,
        method="POST",
        headers={
            "x-api-key": API_KEY,
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return True, f"{resp.status} {resp.read().decode()[:200]}"
    except urllib.error.HTTPError as exc:
        return True, f"HTTP {exc.code} {exc.read().decode()[:200]}"
    except Exception as exc:  # noqa: BLE001
        return False, f"{type(exc).__name__}: {exc}"


def main() -> None:
    attempts = 200
    for i in range(1, attempts + 1):
        # Try stop first (lighter), then delete — either one frees the server.
        if i % 3 == 0:
            ok, msg = call("application.stop", {"applicationId": APP_ID}, timeout=9)
            kind = "stop"
        else:
            ok, msg = call("application.delete", {"applicationId": APP_ID}, timeout=9)
            kind = "delete"
        ts = time.strftime("%H:%M:%S")
        print(f"[{ts}] {i}/{attempts} {kind}: {'OK' if ok else 'fail'} - {msg}", flush=True)
        if ok and kind == "delete":
            print("DELETE_SUCCESS", flush=True)
            return
        time.sleep(1.2)
    print("DELETE_GIVEUP", flush=True)


if __name__ == "__main__":
    main()
