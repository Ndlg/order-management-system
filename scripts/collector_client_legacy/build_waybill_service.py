# -*- coding: utf-8 -*-
import shutil
import subprocess
import sys
import os
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PROJECT_ROOT = Path(__file__).resolve().parents[2]
SOURCE_ROOT = PROJECT_ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from app_info import build_slug

BUILD_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BUILD_SUFFIX = os.environ.get("ORDER_WAYBILL_BUILD_SUFFIX", "").strip()
BUILD_NAME = os.environ.get("ORDER_WAYBILL_BUILD_NAME", build_slug()).strip() or build_slug()
BUILD_NAME = BUILD_NAME + (f"_{BUILD_SUFFIX}" if BUILD_SUFFIX else "")
DIST = ROOT / f"dist_{BUILD_NAME}_{BUILD_STAMP}"
BUILD = ROOT / f"build_{BUILD_NAME}_{BUILD_STAMP}"
SPEC = ROOT / f"spec_{BUILD_NAME}_{BUILD_STAMP}"


def ensure_inside_root(path):
    path = Path(path).resolve()
    root = ROOT.resolve()
    if root != path and root not in path.parents:
        raise RuntimeError(f"refuse to remove path outside experiment root: {path}")
    return path


def remove_tree(path):
    path = ensure_inside_root(path)
    if path.exists():
        shutil.rmtree(path)


def clean():
    for pattern in (f"dist_{BUILD_NAME}_*", f"build_{BUILD_NAME}_*", f"spec_{BUILD_NAME}_*"):
        for path in ROOT.glob(pattern):
            remove_tree(path)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)


def add_data(path, target="."):
    return f"{Path(path).resolve()};{target}"


def main():
    clean()
    subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "-F",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
            "--specpath",
            str(SPEC),
            "--paths",
            str(SOURCE_ROOT),
            "--name",
            "business_waybill_service",
            "--hidden-import",
            "waybill_collector_reader",
            "--hidden-import",
            "waybill_files",
            "--hidden-import",
            "order_secure_common",
            str(ROOT / "business_waybill_service.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    for name in [
        "business_waybill_service.json",
        "启动业务机面单监控服务.bat",
        "安装业务机面单监控服务-开机自启.bat",
        "卸载业务机面单监控服务-开机自启.bat",
        "查看业务机面单监控服务日志.bat",
        "业务机面单监控服务说明.md",
    ]:
        shutil.copy2(ROOT / name, DIST / name)

    for bat_path in DIST.glob("*.bat"):
        text = bat_path.read_text(encoding="utf-8")
        bat_path.write_text(text, encoding="ascii", newline="\r\n")

    remove_tree(BUILD)
    remove_tree(SPEC)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)
    print(f"Waybill service build finished: {DIST}")


if __name__ == "__main__":
    main()
