#!/usr/bin/env python3
import json, sys, urllib.request
API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"
req = urllib.request.Request(f"{API}/application.readLogs?applicationId={APP}&tail=60", headers={"x-api-key": KEY})
rt = json.loads(urllib.request.urlopen(req, timeout=60).read().decode())
if isinstance(rt, str) and rt.startswith('"'):
    rt = json.loads(rt)
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
print(rt[-4000:])
