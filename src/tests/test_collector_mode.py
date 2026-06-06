# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path

from core.collector_config import (
    COLLECTION_MODE_FILTERED,
    COLLECTION_MODE_FULL,
    load_collector_config,
    save_collector_config,
    validate_collection_mode,
)
from core.collector_raw_records import append_raw_records, get_raw_record, list_raw_records


class RuntimeEnv:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_env = {
            "ORDER_SORTER_DATA_DIR": os.environ.get("ORDER_SORTER_DATA_DIR"),
            "ORDER_SORTER_OUTPUT_DIR": os.environ.get("ORDER_SORTER_OUTPUT_DIR"),
            "ORDER_SORTER_TEMP_DIR": os.environ.get("ORDER_SORTER_TEMP_DIR"),
        }
        os.environ["ORDER_SORTER_DATA_DIR"] = str(self.root / "data")
        os.environ["ORDER_SORTER_OUTPUT_DIR"] = str(self.root / "output")
        os.environ["ORDER_SORTER_TEMP_DIR"] = str(self.root / "tmp")
        return self.root

    def __exit__(self, exc_type, exc, tb):
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()


class CollectorModeTest(unittest.TestCase):
    def test_default_collection_mode_is_filtered(self) -> None:
        with RuntimeEnv():
            config = load_collector_config()
            self.assertEqual(config["collection_mode"], COLLECTION_MODE_FILTERED)
            self.assertIn(COLLECTION_MODE_FULL, config["allowed_modes"])

    def test_invalid_collection_mode_is_rejected(self) -> None:
        with self.assertRaises(ValueError):
            validate_collection_mode("raw")

    def test_collector_config_api_switches_modes_and_rejects_invalid(self) -> None:
        with RuntimeEnv():
            from ui import app as web_app

            response = web_app.api_collector_config_update({"collection_mode": "full", "updated_by": "web"})
            self.assertEqual(response["collection_mode"], COLLECTION_MODE_FULL)
            self.assertEqual(web_app.api_collector_config()["collection_mode"], COLLECTION_MODE_FULL)

            bad = web_app.api_collector_config_update({"collection_mode": "all", "updated_by": "web"})
            self.assertEqual(bad.status_code, 400)

    def test_full_mode_preserves_unparsed_raw_print_text(self) -> None:
        with RuntimeEnv():
            raw_text = "未知面单格式\nSPECIAL Ω 中文换行\nemoji-like text :)"
            rows = append_raw_records(
                [{"print_text": raw_text, "task_id": "T1", "document_id": "D1"}],
                collection_mode=COLLECTION_MODE_FULL,
                collector_id="collector-test",
                batch_id="B1",
                collector_version="test",
            )
            self.assertEqual(rows[0]["collection_mode"], COLLECTION_MODE_FULL)
            self.assertEqual(rows[0]["raw_print_text"], raw_text)
            self.assertEqual(rows[0]["parse_status"], "unparsed")

            listed = list_raw_records(limit=10)
            detail = get_raw_record(listed[0]["record_id"])
            self.assertIsNotNone(detail)
            self.assertEqual(detail["raw_print_text"], raw_text)

    def test_waybill_upload_persists_collection_mode(self) -> None:
        with RuntimeEnv():
            from ui import app as web_app

            save_collector_config(COLLECTION_MODE_FULL, updated_by="web", collector_id="web")
            web_app.WAYBILL_REMOTE_STATE["batch_id"] = "B-UPLOAD"
            web_app.WAYBILL_REMOTE_STATE["status"] = "running"
            web_app.WAYBILL_REMOTE_STATE["uploads"] = {}

            response = web_app.api_waybill_agent_upload(
                {
                    "client_id": "collector-1",
                    "batch_id": "B-UPLOAD",
                    "machine_label": "业务机1",
                    "collection_mode": "full",
                    "collector_version": "test-version",
                    "records": [{"print_text": "无法识别的真实打印原文\n第二行", "task_id": "T2"}],
                }
            )
            self.assertEqual(response["accepted"], 1)
            self.assertEqual(response["collection_mode"], COLLECTION_MODE_FULL)
            detail = get_raw_record(list_raw_records(limit=1)[0]["record_id"])
            self.assertEqual(detail["collection_mode"], COLLECTION_MODE_FULL)
            self.assertIn("无法识别的真实打印原文", detail["raw_print_text"])

            bad = web_app.api_waybill_agent_upload(
                {"client_id": "collector-1", "batch_id": "B-UPLOAD", "collection_mode": "raw", "records": []}
            )
            self.assertEqual(bad.status_code, 400)


if __name__ == "__main__":
    unittest.main()
