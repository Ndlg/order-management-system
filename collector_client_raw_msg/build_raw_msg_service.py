# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE_ROOT = ROOT.parent
BUILD_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BUILD_NAME = os.environ.get("ORDER_RAW_MSG_BUILD_NAME", "raw_msg_v1").strip() or "raw_msg_v1"
DIST = ROOT / f"dist_{BUILD_NAME}_{BUILD_STAMP}"
BUILD = ROOT / f"build_{BUILD_NAME}_{BUILD_STAMP}"
SPEC = ROOT / f"spec_{BUILD_NAME}_{BUILD_STAMP}"


def ensure_inside_root(path: Path) -> Path:
    path = Path(path).resolve()
    root = ROOT.resolve()
    if root != path and root not in path.parents:
        raise RuntimeError(f"refuse to remove path outside raw msg tool root: {path}")
    return path


def remove_tree(path: Path) -> None:
    path = ensure_inside_root(path)
    if path.exists():
        shutil.rmtree(path)


def clean() -> None:
    for pattern in (f"dist_{BUILD_NAME}_*", f"build_{BUILD_NAME}_*", f"spec_{BUILD_NAME}_*"):
        for path in ROOT.glob(pattern):
            remove_tree(path)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)


def main() -> None:
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
            "--name",
            "business_waybill_raw_msg_service",
            str(ROOT / "business_waybill_raw_msg_service.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    for name in [
        "business_waybill_raw_msg_service.json",
        "启动原始面单采集服务.bat",
        "查看原始面单采集服务日志.bat",
        "原始面单采集服务说明.md",
    ]:
        shutil.copy2(ROOT / name, DIST / name)

    for bat_path in DIST.glob("*.bat"):
        text = bat_path.read_text(encoding="utf-8")
        bat_path.write_text(text, encoding="ascii", newline="\r\n")

    remove_tree(BUILD)
    remove_tree(SPEC)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)
    print(f"Raw msg service build finished: {DIST}")


if __name__ == "__main__":
    main()
