#!/usr/bin/env python3
import io
import json
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

try:
    import requests
except ImportError:
    import subprocess

    subprocess.check_call([sys.executable, "-m", "pip", "install", "requests", "-q"])
    import requests

API = "http://217.114.40.67:3000/api"
KEY = "TGhDmuUDkJacphxVZjXubVhNvnvvbVqcEGTonfzqWYYdcSQcalfvOBkFRmxLqIHR"
APP = "yJuZ9FANN1ctYrbdtFa3W"
ROOT = Path(__file__).resolve().parents[1]

build_id = str(int(time.time()))
(ROOT / "build_id.txt").write_text(build_id + "\n")
(ROOT / "bot" / "__init__.py").write_text(f'"""Bot package."""\n__build__ = "{build_id}"\n')

files: set[str] = {"build_id.txt", "Dockerfile", "requirements.txt", "config.py", ".dockerignore"}
for pattern in ("bot/**/*.py", "services/**/*.py"):
    for path in ROOT.glob(pattern):
        files.add(path.relative_to(ROOT).as_posix())

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
    for rel in sorted(files):
        zf.write(ROOT / rel, rel)
zip_bytes = buf.getvalue()
print("zip", len(files), len(zip_bytes))

headers = {"x-api-key": KEY}
for url in (
    f"{API}/application.dropDeployment",
    f"{API}/trpc/application.dropDeployment",
    "https://blob.firstdata.ir/api/application.dropDeployment",
):
    try:
        r = requests.post(
            url,
            headers=headers,
            files={"zip": ("homa-task.zip", zip_bytes, "application/zip")},
            data={"applicationId": APP},
            timeout=300,
        )
        print(url, r.status_code, r.text[:500])
    except Exception as exc:
        print(url, "ERR", exc)
