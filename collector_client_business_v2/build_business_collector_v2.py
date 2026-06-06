# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from app_info import build_slug


ROOT = Path(__file__).resolve().parent
BUILD_STAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
BUILD_NAME = os.environ.get("ORDER_BUSINESS_COLLECTOR_BUILD_NAME", f"{build_slug()}_business_v2").strip() or f"{build_slug()}_business_v2"
DIST = ROOT / f"dist_{BUILD_NAME}_{BUILD_STAMP}"
BUILD = ROOT / f"build_{BUILD_NAME}_{BUILD_STAMP}"
SPEC = ROOT / f"spec_{BUILD_NAME}_{BUILD_STAMP}"


def ensure_inside_root(path: Path) -> Path:
    path = Path(path).resolve()
    root = ROOT.resolve()
    if root != path and root not in path.parents:
        raise RuntimeError(f"refuse to remove path outside collector root: {path}")
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
            "-w",
            "--distpath",
            str(DIST),
            "--workpath",
            str(BUILD),
            "--specpath",
            str(SPEC),
            "--paths",
            str(SOURCE_ROOT),
            "--name",
            "business_waybill_collector_v2",
            "--hidden-import",
            "waybill_collector_reader",
            "--hidden-import",
            "waybill_files",
            "--hidden-import",
            "order_secure_common",
            "--hidden-import",
            "waybill_raw_contract",
            "--hidden-import",
            "waybill_text_parser",
            "--hidden-import",
            "shoe_rule_engine",
            str(ROOT / "business_waybill_collector_v2.py"),
        ],
        cwd=ROOT,
        check=True,
    )

    for name in [
        "business_waybill_collector_v2.json",
        "启动业务机采集工具V2.bat",
        "启动业务机采集工具V2-无界面后台.bat",
        "查看业务机采集工具V2日志.bat",
        "业务机采集工具V2说明.md",
    ]:
        shutil.copy2(ROOT / name, DIST / name)

    for bat_path in DIST.glob("*.bat"):
        text = bat_path.read_text(encoding="utf-8")
        bat_path.write_text(text, encoding="ascii", newline="\r\n")

    remove_tree(BUILD)
    remove_tree(SPEC)
    for cache in ROOT.rglob("__pycache__"):
        remove_tree(cache)
    print(f"Business collector V2 build finished: {DIST}")


if __name__ == "__main__":
    main()
