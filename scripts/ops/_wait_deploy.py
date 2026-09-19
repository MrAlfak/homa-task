#!/usr/bin/env python3
import json, sys, time, urllib.request
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"

def api(path):
    req = urllib.request.Request(f"{API}/{path}", headers={"x-api-key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
for i in range(40):
    dep = api(f"deployment.allByType?id={APP}&type=application")[0]
    status = dep.get("status")
    print(f"poll {i+1}: {status} {dep.get('deploymentId')}")
    if status in ("done", "error"):
        log = api(f"deployment.readLogs?deploymentId={dep['deploymentId']}")
        if isinstance(log, str) and log.startswith('"'):
            log = json.loads(log)
        print("--- tail ---")
        print(str(log)[-3000:])
        app = api(f"application.one?applicationId={APP}")
        d = app.get("data", app)
        print("app:", d.get("applicationStatus"))
        raise SystemExit(0 if status == "done" else 1)
    time.sleep(15)
print("TIMEOUT")
raise SystemExit(1)
