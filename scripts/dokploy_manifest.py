"""Upload project source files to Dokploy via patch.saveFileAsPatch."""

from __future__ import annotations

import json
import sys
from pathlib import Path

APP_ID = "ZTVQekZHYAAgnDEQD90mT"
ROOT = Path(__file__).resolve().parent.parent

FILES = [
    "Dockerfile",
    "requirements.txt",
    "config.py",
    ".dockerignore",
    "bot/__init__.py",
    "bot/main.py",
    "bot/keyboards.py",
    "bot/states.py",
    "bot/handlers/__init__.py",
    "bot/handlers/start.py",
    "bot/handlers/admin_tasks.py",
    "bot/handlers/employee_tasks.py",
    "bot/handlers/ideas.py",
    "services/__init__.py",
    "services/sheets.py",
    "services/auth.py",
]


def main() -> int:
    manifest: list[dict[str, str]] = []
    for rel in FILES:
        path = ROOT / rel
        if not path.exists():
            print(f"missing: {rel}", file=sys.stderr)
            return 1
        manifest.append(
            {
                "id": APP_ID,
                "type": "application",
                "filePath": rel.replace("\\", "/"),
                "content": path.read_text(encoding="utf-8"),
                "patchType": "create",
            }
        )
    out = ROOT / "_dokploy_manifest.json"
    out.write_text(json.dumps(manifest, ensure_ascii=False), encoding="utf-8")
    print(f"manifest: {out} ({len(manifest)} files)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
