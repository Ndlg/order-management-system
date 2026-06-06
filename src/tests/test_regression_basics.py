# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import re
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from core.order_core import merge_size_quantity, normalize_qty
from core.waybill_raw_pipeline import parse_raw_waybill_records
from utils.order_secure_common import _source_project_root, get_output_dir, get_temp_dir


class RegressionBasicsTest(unittest.TestCase):
    def test_size_quantity_statistic_expands_quantities(self) -> None:
        rows = pd.DataFrame([{"尺码": "42", "数量": 2}, {"尺码": "41", "数量": 1}])
        self.assertEqual(merge_size_quantity(rows), "41 42 42")

    def test_order_merge_quantity_normalization(self) -> None:
        self.assertEqual(normalize_qty("2.0"), 2)
        self.assertEqual(normalize_qty(""), 1)
        rows = pd.DataFrame([{"尺码": "40", "数量": 1}, {"尺码": "40", "数量": 2}])
        self.assertEqual(merge_size_quantity(rows), "40 40 40")

    def test_image_embedding_smoke(self) -> None:
        temp_dir = Path(get_temp_dir())
        temp_dir.mkdir(parents=True, exist_ok=True)
        image_path = temp_dir / "test_image_embed.png"
        self.addCleanup(lambda: image_path.unlink(missing_ok=True))
        PILImage.new("RGB", (8, 8), "white").save(image_path)
        workbook = Workbook()
        sheet = workbook.active
        sheet.add_image(XLImage(str(image_path)), "A1")
        self.assertEqual(len(sheet._images), 1)

    def test_raw_waybill_parser_accepts_empty_batch(self) -> None:
        self.assertEqual(parse_raw_waybill_records([]), [])

    def test_runtime_output_uses_configured_directory(self) -> None:
        configured = os.environ.get("ORDER_SORTER_OUTPUT_DIR")
        if configured:
            self.assertEqual(Path(get_output_dir()).resolve(), Path(configured).resolve())

    def test_version_executables_share_project_data_root(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        version_bin = project_root / "versions" / "v7.9.3" / "bin"
        self.assertEqual(_source_project_root(version_bin), project_root)

    def test_source_root_contains_only_packages(self) -> None:
        src_root = Path(__file__).resolve().parents[1]
        misplaced_modules = [path.name for path in src_root.glob("*.py")]
        self.assertEqual(misplaced_modules, [])
        for package in ("core", "ui", "utils", "plugins", "tests"):
            self.assertTrue((src_root / package).is_dir(), package)

    def test_code_uses_package_import_boundaries(self) -> None:
        project_root = Path(__file__).resolve().parents[2]
        forbidden = re.compile(
            r"^\s*(?:from|import)\s+("
            r"app|app_info|five_field_normalizer|order_core|order_secure_common|"
            r"qt_app|qt_admin|qt_client|qt_web_console|shoe_rule_engine|"
            r"sku_image_binder|waybill_[a-z_]+"
            r")\b",
            flags=re.MULTILINE,
        )
        offenders: list[str] = []
        for folder in (project_root / "src", project_root / "scripts"):
            for path in folder.rglob("*.py"):
                text = path.read_text(encoding="utf-8", errors="ignore")
                if forbidden.search(text):
                    offenders.append(str(path.relative_to(project_root)))
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
