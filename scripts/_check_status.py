#!/usr/bin/env python3
import json, sys, urllib.request
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"

def api(path):
    req = urllib.request.Request(f"{API}/{path}", headers={"x-api-key": KEY})
    return json.loads(urllib.request.urlopen(req, timeout=120).read().decode())

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
dep = api(f"deployment.allByType?id={APP}&type=application")[0]
print("status:", dep.get("status"), "title:", dep.get("title"))
log = api(f"deployment.readLogs?deploymentId={dep['deploymentId']}")
if isinstance(log, str) and log.startswith('"'):
    log = json.loads(log)
print("has create_task_flow:", "create_task_flow" in log)
print("grep step:", "grep -q" in log)
print("build_id in log:", "1783607708" in log or "1783597458" in log)
print(log[-3500:])
app = api(f"application.one?applicationId={APP}")
d = app.get("data", app) if isinstance(app, dict) else app
print("app status:", d.get("applicationStatus"))
rt = api(f"application.readLogs?applicationId={APP}&tail=30")
if isinstance(rt, str) and rt.startswith('"'):
    rt = json.loads(rt)
print("runtime build:", [line for line in rt.splitlines() if "Running build" in line][-1:] if isinstance(rt,str) else rt)
