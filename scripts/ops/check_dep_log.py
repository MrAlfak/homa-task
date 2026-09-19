#!/usr/bin/env python3
import json
import urllib.request

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"

req = urllib.request.Request(
    f"{API}/deployment.allByType?id={APP}&type=application",
    headers={"x-api-key": KEY},
)
deps = json.loads(urllib.request.urlopen(req).read())
dep = deps[0]
dep_id = dep["deploymentId"]
print("dep:", dep.get("title"), dep.get("status"), dep_id)

req2 = urllib.request.Request(
    f"{API}/deployment.readLogs?deploymentId={dep_id}",
    headers={"x-api-key": KEY},
)
log = urllib.request.urlopen(req2).read().decode()
if log.startswith('"'):
    log = json.loads(log)
needles = ("COPY bot", "COPY build", "RUN test", "CACHED", "DONE", "Docker build")
for line in log.replace("\\n", "\n").splitlines():
    s = line.strip()
    if s.startswith("#1") or any(n in s for n in needles):
        print(s[:240])
