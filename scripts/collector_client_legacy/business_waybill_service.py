# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import socket
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any

SOURCE_ROOT = Path(__file__).resolve().parents[2] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import waybill_collector_reader
from waybill_files import record_key


DEFAULT_CONFIG = {
    "order_server_url": "http://127.0.0.1:8000",
    "poll_interval_seconds": 2,
    "machine_name": "",
    "machine_label": "",
}

def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return base_dir() / "business_waybill_service.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("business_waybill_service.json must be a JSON object")
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    return merged


def post_json(server_url: str, path: str, payload: dict[str, Any]) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{server_url.rstrip('/')}{path}",
        data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def parse_task_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def is_fresh_record(record: dict[str, Any], baseline_keys: set[str], baseline_task_times: dict[str, str]) -> bool:
    key = record_key(record)
    if not key:
        return True
    if key not in baseline_keys:
        return True
    current_dt = parse_task_time(record.get("task_time"))
    baseline_dt = parse_task_time(baseline_task_times.get(key))
    return bool(current_dt and baseline_dt and current_dt > baseline_dt)


def component_db_id(record: dict[str, Any]) -> str:
    return str(record.get("component_db_id") or record.get("component_db_path") or "").strip().lower()


def component_rowid(record: dict[str, Any]) -> int:
    try:
        return int(record.get("component_rowid") or 0)
    except (TypeError, ValueError):
        return 0


def baseline_component_rowids(records: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in records:
        db_id = component_db_id(row)
        rowid = component_rowid(row)
        if not db_id or rowid <= 0:
            continue
        result[db_id] = max(result.get(db_id, 0), rowid)
    return result


def is_batch_increment_record(
    record: dict[str, Any],
    baseline_rowids: dict[str, int],
    baseline_keys: set[str],
    baseline_task_times: dict[str, str],
) -> bool:
    db_id = component_db_id(record)
    rowid = component_rowid(record)
    if db_id and rowid > 0:
        baseline = baseline_rowids.get(db_id)
        if baseline is None:
            return True
        if rowid > baseline:
            return True
        if not record_key(record):
            return False
        return is_fresh_record(record, baseline_keys, baseline_task_times)
    return is_fresh_record(record, baseline_keys, baseline_task_times)


def log(message: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    log_dir = base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "business_waybill_service.log").open("a", encoding="utf-8") as file:
        file.write(line + "\n")


def raw_upload_record(record: dict[str, Any], index: int = 0) -> dict[str, Any]:
    raw_text = str(record.get("打印信息") or record.get("print_text_raw") or record.get("print_text") or "").strip()
    if not raw_text:
        raw_text = "[无打印信息]"
    return {
        "打印信息": raw_text,
        "task_id": str(record.get("task_id") or ""),
        "document_id": str(record.get("document_id") or ""),
        "task_time": str(record.get("task_time") or ""),
        "source_record_index": index,
        "extract_status": str(record.get("extract_status") or ""),
        "component_name": str(record.get("component_name") or ""),
        "component_db_path": str(record.get("component_db_path") or ""),
        "component_rowid": component_rowid(record),
    }


class BusinessWaybillService:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.server_url = str(os.environ.get("ORDER_WAYBILL_SERVER_URL") or cfg.get("order_server_url") or "").strip().rstrip("/")
        self.poll_interval = max(1.0, float(cfg.get("poll_interval_seconds") or 2))
        self.machine_name = str(cfg.get("machine_name") or socket.gethostname()).strip() or socket.gethostname()
        self.machine_label = str(cfg.get("machine_label") or self.machine_name).strip() or self.machine_name
        self.client_id = f"standalone-{self.machine_name}-{getpass.getuser()}"
        self.active_batch_id = ""
        self.baseline_keys: set[str] = set()
        self.baseline_task_times: dict[str, str] = {}
        self.baseline_rowids: dict[str, int] = {}
        self.uploaded_batches: set[str] = set()
        self.stop_event = threading.Event()
        self.last_error_text = ""
        self.last_error_log_at = 0.0

    def run(self) -> None:
        if not self.server_url:
            raise RuntimeError("order_server_url is empty in business_waybill_service.json")
        log(f"service_start server={self.server_url} machine={self.machine_label}")
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.log_connect_wait(exc)
            self.stop_event.wait(self.poll_interval)

    def log_connect_wait(self, exc: Exception) -> None:
        text = str(exc)
        now = time.time()
        if text == self.last_error_text and now - self.last_error_log_at < 30:
            return
        self.last_error_text = text
        self.last_error_log_at = now
        log(f"waiting_order_server server={self.server_url} reason={text}")

    def tick(self) -> None:
        response = post_json(
            self.server_url,
            "/api/waybill/agent/poll",
            {
                "client_id": self.client_id,
                "machine_name": self.machine_name,
                "machine_label": self.machine_label,
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "platform": platform.platform(),
                "active_batch_id": self.active_batch_id,
                "components": waybill_collector_reader.component_status(),
            },
        )
        if not response.get("ok"):
            log(f"poll_rejected {response}")
            return
        command = str(response.get("command") or "idle").lower()
        batch_id = str(response.get("batch_id") or "")
        if command == "start" and batch_id:
            self.start_batch(batch_id)
        elif command == "stop" and batch_id:
            self.stop_batch(batch_id)

    def start_batch(self, batch_id: str) -> None:
        if self.active_batch_id == batch_id:
            return
        records = waybill_collector_reader.collect_records()
        self.active_batch_id = batch_id
        keyed_records = [(record_key(row), row) for row in records]
        self.baseline_keys = {key for key, _row in keyed_records if key}
        self.baseline_task_times = {key: str(row.get("task_time") or "") for key, row in keyed_records if key}
        self.baseline_rowids = baseline_component_rowids(records)
        component_text = ",".join(f"{Path(db_id).name}:{rowid}" for db_id, rowid in sorted(self.baseline_rowids.items()))
        log(f"batch_start batch={batch_id} baseline={len(records)} components={component_text}")

    def stop_batch(self, batch_id: str) -> None:
        if batch_id in self.uploaded_batches:
            return
        if self.active_batch_id != batch_id:
            self.start_batch(batch_id)
        records = waybill_collector_reader.collect_records()
        batch_records = [
            row
            for row in records
            if is_batch_increment_record(row, self.baseline_rowids, self.baseline_keys, self.baseline_task_times)
        ]
        response = post_json(
            self.server_url,
            "/api/waybill/agent/upload",
            {
                "client_id": self.client_id,
                "machine_name": self.machine_name,
                "machine_label": self.machine_label,
                "hostname": socket.gethostname(),
                "username": getpass.getuser(),
                "batch_id": batch_id,
                "records": [raw_upload_record(row, index) for index, row in enumerate(batch_records, 1)],
                "records_found": len(batch_records),
                "records_scanned": len(records),
                "capture_mode": "raw_waybill",
                "upload_mode": "batch_rowid_increment_preserve_all_content",
            },
        )
        if response.get("ok"):
            self.uploaded_batches.add(batch_id)
            self.active_batch_id = ""
            log(
                f"batch_uploaded batch={batch_id} records={len(batch_records)} "
                f"found={len(records)} mode=batch_rowid_increment_preserve_all_content"
            )
        else:
            log(f"upload_rejected batch={batch_id} response={response}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Standalone business waybill monitor service")
    parser.add_argument("--print-config", action="store_true", help="print the current config path and exit")
    args = parser.parse_args()
    if args.print_config:
        print(config_path())
        return
    service = BusinessWaybillService(load_config())
    service.run()


if __name__ == "__main__":
    main()
