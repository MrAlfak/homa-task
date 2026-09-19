#!/usr/bin/env python3
import json, sys, urllib.request
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
DEP = sys.argv[1] if len(sys.argv) > 1 else "wHw4lxUyY8vpZ_uJa01dK"
req = urllib.request.Request(
    f"{API}/deployment.readLogs?deploymentId={DEP}",
    headers={"x-api-key": KEY},
)
log = urllib.request.urlopen(req, timeout=120).read().decode()
if log.startswith('"'):
    log = json.loads(log)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(log[-8000:])
