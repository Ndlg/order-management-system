# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import logging
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from plugins.collector_agent import agent_db_reader, agent_storage
from plugins.collector_agent.agent_config import config_path, load_config
from plugins.collector_agent.agent_models import AGENT_VERSION, PROTOCOL_VERSION
from plugins.collector_agent.agent_service import CollectorAgentService


class RuntimeEnv:
    def __enter__(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.old_env = {
            "ORDER_SORTER_DATA_DIR": os.environ.get("ORDER_SORTER_DATA_DIR"),
            "ORDER_SORTER_OUTPUT_DIR": os.environ.get("ORDER_SORTER_OUTPUT_DIR"),
            "ORDER_SORTER_TEMP_DIR": os.environ.get("ORDER_SORTER_TEMP_DIR"),
            "ORDER_COLLECTOR_DATA_DIR": os.environ.get("ORDER_COLLECTOR_DATA_DIR"),
            "ORDER_COLLECTOR_DB_PATHS": os.environ.get("ORDER_COLLECTOR_DB_PATHS"),
        }
        os.environ["ORDER_SORTER_DATA_DIR"] = str(self.root / "data")
        os.environ["ORDER_SORTER_OUTPUT_DIR"] = str(self.root / "output")
        os.environ["ORDER_SORTER_TEMP_DIR"] = str(self.root / "tmp")
        os.environ["ORDER_COLLECTOR_DATA_DIR"] = str(self.root / "collector")
        return self.root

    def __exit__(self, exc_type, exc, tb):
        logging.shutdown()
        for key, value in self.old_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        self.temp.cleanup()


def make_print_xml(text: str) -> str:
    return f"<root><text><![CDATA[{text}]]></text></root>"


def make_payload(documents: list[dict]) -> str:
    return json.dumps({"task": {"taskID": "payload-task", "documents": documents}}, ensure_ascii=False)


def make_document(document_id: str, print_xml: str) -> dict:
    return {"documentID": document_id, "contents": [{"printXML": print_xml, "data": {"ignored": "server-side-only"}}]}


def create_sample_db(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    try:
        con.execute("create table task (taskID text, msg text, time text)")
        rows = [
            ("T1", make_payload([make_document("D1", make_print_xml("商品A 42 1"))]), "2026-06-07 10:00:01"),
            ("T_BAD", "{bad-json", "2026-06-07 10:00:02"),
            ("T_NO_DOC", make_payload([]), "2026-06-07 10:00:03"),
            ("T_XML_BAD", make_payload([make_document("D_XML", "<root><text><![CDATA[破损XML]]></root>")]), "2026-06-07 10:00:04"),
            ("T_EMPTY", make_payload([make_document("D_EMPTY", "")]), "2026-06-07 10:00:05"),
            ("T_DUP", make_payload([make_document("D_DUP", make_print_xml("重复文本"))]), "2026-06-07 10:00:06"),
            ("T_DUP", make_payload([make_document("D_DUP", make_print_xml("重复文本"))]), "2026-06-07 10:00:07"),
        ]
        con.executemany("insert into task (taskID, msg, time) values (?, ?, ?)", rows)
        con.commit()
    finally:
        con.close()


class CollectorAgentTest(unittest.TestCase):
    def test_db_reader_preserves_every_task_rowid_and_fallback_status(self) -> None:
        with RuntimeEnv() as root:
            db_path = root / "CNPrintTool" / "resources" / "print.db"
            create_sample_db(db_path)
            os.environ["ORDER_COLLECTOR_DB_PATHS"] = str(db_path)

            records = agent_db_reader.collect_records({}, agent_db_reader.current_max_rowids(), batch_id="B1")
            rowids = {int(row["component_rowid"]) for row in records}
            self.assertEqual(rowids, set(range(1, 8)))
            statuses = {row["extract_status"] for row in records}
            self.assertIn("raw_json_parse_failed", statuses)
            self.assertIn("no_documents", statuses)
            self.assertIn("print_xml_parse_failed", statuses)
            self.assertIn("empty_print_text", statuses)
            duplicate_rows = [row for row in records if row.get("task_id") == "T_DUP"]
            self.assertEqual(len(duplicate_rows), 2)
            self.assertEqual({int(row["component_rowid"]) for row in duplicate_rows}, {6, 7})

    def test_backend_bind_poll_upload_auth_and_dedupe_by_rowid(self) -> None:
        with RuntimeEnv():
            from ui import app as web_app

            web_app.WAYBILL_REMOTE_STATE.update(
                {
                    "status": "idle",
                    "batch_id": "",
                    "started_at": "",
                    "stopped_at": "",
                    "collectors": {},
                    "uploads": {},
                    "last_raw_file": "",
                    "last_raw_count": 0,
                    "last_processed_file": "",
                    "last_processed_count": 0,
                }
            )
            bind_code = web_app.api_collector_bind_code({})["bind_code"]
            bind = web_app.api_collector_bind(
                {
                    "bind_code": bind_code,
                    "client_id": "agent-1",
                    "machine_name": "biz-01",
                    "machine_label": "业务机01",
                    "agent_version": AGENT_VERSION,
                    "protocol_version": PROTOCOL_VERSION,
                }
            )
            self.assertTrue(bind["ok"])
            token = bind["agent_token"]

            web_app.api_waybill_start()
            poll = web_app.api_collector_poll(
                {
                    "client_id": "agent-1",
                    "machine_name": "biz-01",
                    "machine_label": "业务机01",
                    "agent_version": AGENT_VERSION,
                    "protocol_version": PROTOCOL_VERSION,
                    "component_status": [],
                },
                authorization=f"Bearer {token}",
            )
            self.assertEqual(poll["command"], "start")

            bad = web_app.api_collector_upload({"client_id": "agent-1", "batch_id": poll["batch_id"], "records": []})
            self.assertEqual(bad.status_code, 401)

            base_record = {
                "component_name": "CNPrintTool",
                "component_db_id": "db-1",
                "component_db_path": "print.db",
                "task_id": "T_DUP",
                "document_id": "D_DUP",
                "source_record_index": 1,
                "raw_msg_json": "{}",
                "raw_document_json": "{}",
                "print_text_raw": "重复文本",
                "extract_status": "raw_preserved",
            }
            records = [
                {**base_record, "component_rowid": 1},
                {**base_record, "component_rowid": 1},
                {**base_record, "component_rowid": 2},
            ]
            upload = web_app.api_collector_upload(
                {
                    "client_id": "agent-1",
                    "batch_id": poll["batch_id"],
                    "machine_name": "biz-01",
                    "machine_label": "业务机01",
                    "agent_version": AGENT_VERSION,
                    "protocol_version": PROTOCOL_VERSION,
                    "records": records,
                },
                authorization=f"Bearer {token}",
            )
            self.assertEqual(upload["accepted"], 2)
            listed = web_app.api_collector_records(limit=10)["records"]
            self.assertEqual(len(listed), 2)
            self.assertEqual({str(row["component_rowid"]) for row in listed}, {"1", "2"})

    def test_pending_upload_written_on_failure_and_cleaned_after_success(self) -> None:
        with RuntimeEnv() as root:
            db_path = root / "CloudPrintClient" / "resources" / "print.db"
            create_sample_db(db_path)
            os.environ["ORDER_COLLECTOR_DB_PATHS"] = str(db_path)
            config = load_config()
            config.update({"client_id": "agent-pending", "agent_token": "token", "server_url": "http://127.0.0.1:9"})
            service = CollectorAgentService(config)
            batch_id = "B-PENDING"
            agent_storage.save_batch_baseline(batch_id, {agent_db_reader.component_db_id(db_path): 0})

            def fail_upload(payload):
                raise RuntimeError("offline")

            service.upload_payload = fail_upload  # type: ignore[method-assign]
            result = service.handle_stop(batch_id)
            self.assertTrue(result["pending"])
            self.assertEqual(len(agent_storage.iter_pending_uploads()), 1)

            uploaded = []

            def ok_upload(payload):
                uploaded.append(payload)
                return True

            service.upload_payload = ok_upload  # type: ignore[method-assign]
            self.assertEqual(service.flush_pending_uploads(), 1)
            self.assertEqual(len(agent_storage.iter_pending_uploads()), 0)
            self.assertTrue(uploaded)

    def test_agent_config_stays_in_runtime_data_dir(self) -> None:
        with RuntimeEnv() as root:
            cfg = load_config()
            self.assertEqual(cfg["agent_version"], AGENT_VERSION)
            self.assertTrue(str(config_path()).startswith(str(root / "collector")))


if __name__ == "__main__":
    unittest.main()
