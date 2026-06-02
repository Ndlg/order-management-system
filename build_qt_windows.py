# -*- coding: utf-8 -*-
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

from app_info import build_slug


ROOT = Path(__file__).resolve().parent
BUILD_ROOT = ROOT.parent / "build"
BUILD_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BUILD_SLUG = os.environ.get("ORDER_SORTER_BUILD_SLUG", build_slug())
DIST = BUILD_ROOT / f"dist_qt_{BUILD_SLUG}_{BUILD_STAMP}"
BUILD = BUILD_ROOT / f"build_qt_{BUILD_SLUG}_{BUILD_STAMP}"
SPEC = BUILD_ROOT / f"spec_qt_{BUILD_SLUG}_{BUILD_STAMP}"


def ensure_inside_root(path):
    path = Path(path).resolve()
    allowed_roots = (ROOT.resolve(), BUILD_ROOT.resolve())
    if not any(root == path or root in path.parents for root in allowed_roots):
        raise RuntimeError(f"refuse to remove path outside source/build root: {path}")
    return path


def remove_tree(path):
    path = ensure_inside_root(path)
    if path.exists():
        shutil.rmtree(path)


def stop_processes_using(path):
    path = ensure_inside_root(path)
    if not path.exists():
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


def clean():
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    for pattern in (f"dist_qt_{BUILD_SLUG}_*", f"build_qt_{BUILD_SLUG}_*", f"spec_qt_{BUILD_SLUG}_*"):
        for path in BUILD_ROOT.glob(pattern):
            if path.name.startswith(f"dist_qt_{BUILD_SLUG}_"):
                stop_processes_using(path)
            remove_tree(path)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)


def run_pyinstaller(args):
    common = [
        sys.executable,
        str(ROOT / "pyinstaller_no_checksum.py"),
        "--noconfirm",
        "--clean",
        "-F",
        "-w",
        "--distpath",
        str(DIST),
        "--workpath",
        str(BUILD),
        "--specpath",
        str(SPEC),
        "--hidden-import",
        "PySide6.QtCore",
        "--hidden-import",
        "PySide6.QtGui",
        "--hidden-import",
        "PySide6.QtWidgets",
        "--hidden-import",
        "PySide6.QtNetwork",
        "--hidden-import",
        "app_info",
        "--hidden-import",
        "order_secure_common",
        "--hidden-import",
        "five_field_normalizer",
        "--hidden-import",
        "waybill_files",
        "--hidden-import",
        "waybill_raw_contract",
        "--hidden-import",
        "waybill_raw_pipeline",
        "--hidden-import",
        "waybill_text_parser",
        "--hidden-import",
        "shoe_rule_engine",
    ]
    print("RUN:", " ".join(common + args), flush=True)
    subprocess.run(common + args, cwd=ROOT, check=True)


def rename_exe(temp_name, final_name):
    source = DIST / f"{temp_name}.exe"
    target = DIST / f"{final_name}.exe"
    if not source.exists():
        raise FileNotFoundError(source)
    last_error = None
    for _ in range(60):
        try:
            if target.exists():
                target.unlink()
            source.rename(target)
            return
        except PermissionError as exc:
            last_error = exc
            time.sleep(0.5)
    raise last_error or PermissionError(source)


def add_data(path, target="."):
    return f"{Path(path).resolve()};{target}"


def main():
    clean()
    run_pyinstaller(
        [
            "--name",
            "order_admin_app",
            "--icon",
            str(ROOT / "icon_backend.ico"),
            "--add-data",
            add_data(ROOT / "icon_backend.ico"),
            "--add-data",
            add_data(ROOT / "icon_backend.png"),
            str(ROOT / "qt_admin.py"),
        ]
    )
    rename_exe("order_admin_app", "订单整理管理系统")
    run_pyinstaller(
        [
            "--name",
            "order_client_app",
            "--icon",
            str(ROOT / "icon_frontend.ico"),
            "--add-data",
            add_data(ROOT / "icon_frontend.ico"),
            "--add-data",
            add_data(ROOT / "icon_frontend.png"),
            "--hidden-import",
            "order_core",
            str(ROOT / "qt_client.py"),
        ]
    )
    rename_exe("order_client_app", "一键整理订单")
    run_pyinstaller(
        [
            "--name",
            "order_web_console",
            "--icon",
            str(ROOT / "icon_web.ico"),
            "--add-data",
            add_data(ROOT / "icon_web.ico"),
            "--add-data",
            add_data(ROOT / "icon_web.png"),
            "--add-data",
            add_data(ROOT / "templates", "templates"),
            "--hidden-import",
            "app",
            "--hidden-import",
            "order_core",
            "--collect-all",
            "fastapi",
            "--collect-all",
            "starlette",
            "--collect-all",
            "uvicorn",
            str(ROOT / "qt_web_console.py"),
        ]
    )
    rename_exe("order_web_console", "Web服务控制台")
    remove_tree(BUILD)
    remove_tree(SPEC)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)
    print(f"Qt experiment build finished: {DIST}")


if __name__ == "__main__":
    main()
