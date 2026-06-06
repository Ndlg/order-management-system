# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import unittest
from pathlib import Path

import pandas as pd
from openpyxl import Workbook
from openpyxl.drawing.image import Image as XLImage
from PIL import Image as PILImage

from order_core import merge_size_quantity, normalize_qty
from order_secure_common import get_output_dir, get_temp_dir
from waybill_raw_pipeline import parse_raw_waybill_records


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


if __name__ == "__main__":
    unittest.main()
