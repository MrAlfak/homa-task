#!/usr/bin/env python3
"""Build portable HomaTask-windows.zip with pre-extracted Python and dependencies."""

from __future__ import annotations

import os
import shutil
import subprocess
import tarfile
import time
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CACHE = ROOT / ".tools" / "cache"
TOOLS = ROOT / ".tools"
DIST = ROOT / "dist"
BUILD_DIR = DIST / "_build_windows"
APP_DIR = BUILD_DIR / "HomaTask"
ZIP_OUTPUT = DIST / "HomaTask-windows.zip"

_STRIP_DIRS = frozenset({
    "tcl",
    "tk",
    "include",
    "libs",
    "idlelib",
    "turtledemo",
    "ensurepip",
    "tkinter",
    "idle",
    "test",
    "tests",
})
_STRIP_FILES = frozenset({"pythonw.exe", "pythonw.pdb"})
_STRIP_SUFFIXES = frozenset({".pdb", ".pyc"})


def copy_tree(src: Path, dst: Path) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(
        src,
        dst,
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )


def extract_python(archive: Path, dest_python: Path) -> None:
    print("Extracting Python runtime...", flush=True)
    if dest_python.exists():
        shutil.rmtree(dest_python)
    dest_python.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive, "r:gz") as tf:
        # Filter out dangerous paths / symlinks if any
        tf.extractall(dest_python.parent)
    extracted = dest_python.parent / "python"
    if extracted != dest_python and extracted.exists():
        shutil.move(str(extracted), str(dest_python))


def install_wheels(wheel_dir: Path, site_packages: Path) -> None:
    print("Pre-installing wheels into site-packages...", flush=True)
    site_packages.mkdir(parents=True, exist_ok=True)
    wheels = sorted(wheel_dir.glob("*.whl"))
    for wheel in wheels:
        with zipfile.ZipFile(wheel) as zf:
            zf.extractall(site_packages)
    print(f"Installed {len(wheels)} wheels.", flush=True)


def strip_unused(python_dir: Path) -> None:
    print("Stripping debug symbols and unused dirs...", flush=True)
    drop_dirs: list[Path] = []
    drop_files: list[Path] = []
    for path in python_dir.rglob("*"):
        if path.is_dir() and path.name.lower() in _STRIP_DIRS:
            drop_dirs.append(path)
        elif path.is_file() and (
            path.suffix.lower() in _STRIP_SUFFIXES or path.name.lower() in _STRIP_FILES
        ):
            drop_files.append(path)
    for path in drop_files:
        path.unlink(missing_ok=True)
    for path in sorted(drop_dirs, key=lambda item: len(item.parts), reverse=True):
        shutil.rmtree(path, ignore_errors=True)


def build_launcher() -> Path:
    print("Compiling HomaTask.exe with Go...", flush=True)
    go_bin = TOOLS / "go" / "bin" / "go"
    launcher_src = ROOT / "packaging" / "windows" / "launcher.go"
    out_exe = ROOT / "packaging" / "windows" / "HomaTask.exe"
    env = os.environ.copy()
    env["GOOS"] = "windows"
    env["GOARCH"] = "amd64"
    env["CGO_ENABLED"] = "0"
    subprocess.check_call(
        [str(go_bin), "build", "-trimpath", "-ldflags=-s -w", "-o", str(out_exe), str(launcher_src)],
        env=env,
    )
    return out_exe


def zip_folder(src: Path, dest_zip: Path) -> None:
    print(f"Creating zip archive {dest_zip.name}...", flush=True)
    dest_zip.parent.mkdir(parents=True, exist_ok=True)
    if dest_zip.exists():
        dest_zip.unlink()
    with zipfile.ZipFile(dest_zip, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        # Store files under HomaTask/ prefix
        base_dir = src.parent
        for path in sorted(src.rglob("*")):
            if not path.is_file():
                continue
            archive_path = path.relative_to(base_dir).as_posix()
            zf.write(path, archive_path)


def main() -> None:
    stamp = str(int(time.time()))
    print(f"--- Building HomaTask Windows Distribution (Build {stamp}) ---")

    DIST.mkdir(parents=True, exist_ok=True)
    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
    APP_DIR.mkdir(parents=True)

    # 1. Compile launcher
    launcher_exe = build_launcher()
    shutil.copy2(launcher_exe, APP_DIR / "HomaTask.exe")

    # 2. Extract and prepare Python
    python_tar = CACHE / "python-win.tar.gz"
    python_dir = APP_DIR / "python"
    extract_python(python_tar, python_dir)

    # 3. Copy python312._pth to enable site-packages
    pth_src = ROOT / "packaging" / "windows" / "python312._pth"
    shutil.copy2(pth_src, python_dir / "python312._pth")

    # 4. Install wheels
    wheels_dir = CACHE / "wheels" / "win"
    site_packages = python_dir / "Lib" / "site-packages"
    install_wheels(wheels_dir, site_packages)

    # 5. Strip debug files
    strip_unused(python_dir)

    # 6. Copy app files
    print("Copying bot, services, assets, and configs...", flush=True)
    copy_tree(ROOT / "bot", APP_DIR / "bot")
    copy_tree(ROOT / "services", APP_DIR / "services")
    copy_tree(ROOT / "assets", APP_DIR / "assets")

    shutil.copy2(ROOT / "config.py", APP_DIR / "config.py")
    shutil.copy2(ROOT / "packaging" / "windows" / "run.py", APP_DIR / "run.py")
    shutil.copy2(ROOT / "packaging" / "windows" / "start.bat", APP_DIR / "start.bat")
    shutil.copy2(ROOT / "packaging" / "windows" / "README-WINDOWS.txt", APP_DIR / "README-WINDOWS.txt")
    shutil.copy2(ROOT / "requirements.txt", APP_DIR / "requirements.txt")

    (APP_DIR / "build_id.txt").write_text(stamp, encoding="utf-8")
    (ROOT / "build_id.txt").write_text(stamp, encoding="utf-8")

    # Credentials & environment
    cred_src = ROOT / "credentials" / "google-service-account.json"
    if cred_src.exists():
        cred_dst = APP_DIR / "credentials"
        cred_dst.mkdir(parents=True, exist_ok=True)
        shutil.copy2(cred_src, cred_dst / "google-service-account.json")

    env_src = ROOT / ".env"
    if env_src.exists():
        shutil.copy2(env_src, APP_DIR / ".env")
    env_example = ROOT / ".env.example"
    if env_example.exists():
        shutil.copy2(env_example, APP_DIR / ".env.example")

    # 7. Create Zip
    zip_folder(APP_DIR, ZIP_OUTPUT)

    # 8. Clean up build directory
    shutil.rmtree(BUILD_DIR, ignore_errors=True)

    size_mb = ZIP_OUTPUT.stat().st_size / (1024 * 1024)
    print(f"--- SUCCESS: Created {ZIP_OUTPUT} ({size_mb:.2f} MB) ---")


if __name__ == "__main__":
    main()
