# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src"
SCRIPT_ROOT = PROJECT_ROOT / "scripts"
TMP_BUILD_ROOT = PROJECT_ROOT / "tmp" / "build"
AGENT_ENTRY = SRC_ROOT / "plugins" / "collector_agent" / "agent_app.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build OrderCollectorAgent.")
    parser.add_argument("--version", default="7.9.3", help="Agent version, for example 7.9.3.")
    parser.add_argument("--output-dir", default="", help="Optional directory to copy the final exe into.")
    parser.add_argument("--keep-build", action="store_true", help="Keep PyInstaller work/spec directories.")
    return parser.parse_args()


def normalized_version(raw: str) -> str:
    return str(raw or "").strip().lstrip("vV") or "7.9.3"


def ensure_inside_tmp(path: Path) -> Path:
    resolved = path.resolve()
    root = TMP_BUILD_ROOT.resolve()
    if not (resolved == root or root in resolved.parents):
        raise RuntimeError(f"refuse to remove path outside tmp/build: {resolved}")
    return resolved


def ensure_inside_project(path: Path) -> Path:
    resolved = path.resolve()
    root = PROJECT_ROOT.resolve()
    if not (resolved == root or root in resolved.parents):
        raise RuntimeError(f"refuse to operate outside project: {resolved}")
    return resolved


def remove_tree(path: Path) -> None:
    path = ensure_inside_tmp(path)
    if path.exists():
        shutil.rmtree(path)


def stop_processes_using(path: Path) -> None:
    path = ensure_inside_tmp(path)
    if os.name != "nt" or not path.exists():
        return
    script = r"""
$target = [System.IO.Path]::GetFullPath($env:TARGET_DIR)
Get-Process | Where-Object {
  $_.Path -and [System.IO.Path]::GetFullPath($_.Path).StartsWith($target, [System.StringComparison]::OrdinalIgnoreCase)
} | Stop-Process -Force
"""
    env = os.environ.copy()
    env["TARGET_DIR"] = str(path)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.5)


def stop_project_processes_using(path: Path) -> None:
    path = ensure_inside_project(path)
    if os.name != "nt" or not path.exists():
        return
    script = r"""
$target = [System.IO.Path]::GetFullPath($env:TARGET_DIR)
Get-Process | Where-Object {
  $_.Path -and [System.IO.Path]::GetFullPath($_.Path).StartsWith($target, [System.StringComparison]::OrdinalIgnoreCase)
} | Stop-Process -Force
"""
    env = os.environ.copy()
    env["TARGET_DIR"] = str(path)
    subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    time.sleep(0.5)


def copy_with_retry(source: Path, target: Path, attempts: int = 12) -> None:
    last_error: Exception | None = None
    for _ in range(attempts):
        try:
            shutil.copy2(source, target)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    if last_error:
        raise last_error


def build_agent(version: str, keep_build: bool = False) -> Path:
    version = normalized_version(version)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    exe_name = f"OrderCollectorAgent_v{version}"
    dist = TMP_BUILD_ROOT / f"dist_collector_agent_v{version.replace('.', '_')}_{stamp}"
    build = TMP_BUILD_ROOT / f"build_collector_agent_v{version.replace('.', '_')}_{stamp}"
    spec = TMP_BUILD_ROOT / f"spec_collector_agent_v{version.replace('.', '_')}_{stamp}"
    TMP_BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    stop_processes_using(dist)
    for path in (dist, build, spec):
        remove_tree(path)

    command = [
        sys.executable,
        str(SCRIPT_ROOT / "pyinstaller_no_checksum.py"),
        "--noconfirm",
        "--clean",
        "-F",
        "--distpath",
        str(dist),
        "--workpath",
        str(build),
        "--specpath",
        str(spec),
        "--paths",
        str(SRC_ROOT),
        "--name",
        exe_name,
        "--hidden-import",
        "plugins.collector_agent.agent_app",
        "--hidden-import",
        "plugins.collector_agent.agent_service",
        "--hidden-import",
        "plugins.collector_agent.agent_db_reader",
        "--hidden-import",
        "plugins.collector_agent.agent_storage",
        "--hidden-import",
        "plugins.collector_agent.agent_ui",
        "--hidden-import",
        "plugins.collector_agent.agent_tray",
        "--hidden-import",
        "tkinter",
        str(AGENT_ENTRY),
    ]
    print("RUN:", " ".join(command), flush=True)
    subprocess.run(command, cwd=PROJECT_ROOT, check=True)

    exe = dist / f"{exe_name}.exe"
    if not exe.exists():
        raise FileNotFoundError(exe)
    if not keep_build:
        remove_tree(build)
        remove_tree(spec)
    return exe


def main() -> int:
    args = parse_args()
    exe = build_agent(args.version, keep_build=args.keep_build)
    if args.output_dir:
        target_dir = Path(args.output_dir)
        target_dir.mkdir(parents=True, exist_ok=True)
        stop_project_processes_using(target_dir)
        target = target_dir / exe.name
        copy_with_retry(exe, target)
        exe = target
    print(f"collector_agent_exe={exe}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
