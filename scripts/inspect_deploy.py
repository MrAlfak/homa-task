#!/usr/bin/env python3
"""Inspect: Homa project/env via API + local registry + swarm node via SSH."""

from __future__ import annotations

import json
import ssl
import urllib.request

import paramiko

API = "https://blob.firstdata.ir/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
HOST, USER, PW = "217.114.40.67", "root", "onznbxc1BccO1Ys1"
ctx = ssl.create_default_context()


def api_get(path: str):
    req = urllib.request.Request(f"{API}/{path}", headers={"x-api-key": KEY, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=30, context=ctx) as r:
        return json.loads(r.read().decode())


def main() -> None:
    print("===== PROJECTS / HOMA ENV =====")
    projects = api_get("project.all")
    data = projects.get("data", projects) if isinstance(projects, dict) else projects
    for p in data:
        if "homa" in (p.get("name", "").lower()):
            print("project:", p.get("name"), p.get("projectId"))
            for env in p.get("environments", []):
                print("  env:", env.get("name"), env.get("environmentId"))
            print("  servers:", [s.get("serverId") for s in p.get("servers", [])] if p.get("servers") else "default")

    print("\n===== SSH: registry + node =====")
    c = paramiko.SSHClient()
    c.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    c.connect(HOST, username=USER, password=PW, timeout=30, banner_timeout=120, auth_timeout=120,
              look_for_keys=False, allow_agent=False)
    cmd = r"""
echo '-- registry container --'
docker ps -a --filter name=registry --format '{{.Names}} | {{.Image}} | {{.Status}} | {{.Ports}}'
echo '-- listening ports 5000 --'
ss -ltnp 2>/dev/null | grep -E ':5000' || echo 'no 5000 listener'
echo '-- swarm node --'
docker node ls --format '{{.Hostname}} | {{.Status}} | {{.ManagerStatus}}'
echo '-- docker version --'
docker version --format '{{.Server.Version}}'
"""
    _, o, e = c.exec_command(cmd, timeout=60)
    print(o.read().decode())
    err = e.read().decode().strip()
    if err:
        print("[stderr]", err[:500])
    c.close()


if __name__ == "__main__":
    main()
