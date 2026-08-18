#!/usr/bin/env python3
import json
import time
import urllib.request

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"


def api(method, path, data=None):
    body = json.dumps(data).encode() if data else None
    req = urllib.request.Request(
        f"{API}/{path}",
        data=body,
        method=method,
        headers={"x-api-key": KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=180) as r:
        raw = r.read().decode()
        return json.loads(raw) if raw else {}


build_id = str(int(time.time()))
app = api("GET", f"application.one?applicationId={APP}")
app_name = app.get("appName", "homa-task-bot-qsnkoy")
api("POST", "application.update", {
    "applicationId": APP,
    "cleanCache": True,
    "buildArgs": f"APP_BUILD_ID={build_id}",
})
print("redeploy", build_id)
api("POST", "application.redeploy", {
    "applicationId": APP,
    "title": f"After refresh {build_id}",
    "description": "redeploy_after_refresh.py",
})
dep = {}
for i in range(30):
    time.sleep(5)
    dep = api("GET", f"deployment.allByType?id={APP}&type=application")[0]
    st = dep.get("status")
    print("poll", i + 1, st)
    if st in ("done", "error"):
        break

log = api("GET", f"deployment.readLogs?deploymentId={dep['deploymentId']}")
text = json.loads(log) if isinstance(log, str) and log.startswith('"') else (log if isinstance(log, str) else str(log))
print("grep sheets_async", "sheets_async" in text)
print("grep -q", "grep -q" in text)
print("COPY build_id", "COPY build_id" in text)
print(text[-5000:])

time.sleep(25)
rt = api("GET", f"application.readLogs?applicationId={APP}&tail=60")
rt_text = json.loads(rt) if isinstance(rt, str) and rt.startswith('"') else (rt if isinstance(rt, str) else str(rt))
print("Handlers loaded", "Handlers loaded" in rt_text)
print(rt_text[-2500:])
