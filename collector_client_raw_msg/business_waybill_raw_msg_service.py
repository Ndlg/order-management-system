# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import getpass
import json
import os
import platform
import shutil
import socket
import sqlite3
import sys
import threading
import time
import urllib.request
from datetime import datetime
from pathlib import Path
from typing import Any


DEFAULT_CONFIG = {
    "order_server_url": "http://127.0.0.1:8000",
    "poll_interval_seconds": 2,
    "machine_name": "",
    "machine_label": "",
}

DEFAULT_DBS = [
    Path(r"C:\Program Files (x86)\CNPrintTool\resources\print.db"),
    Path(r"C:\Program Files (x86)\CloudPrintClient\resources\print.db"),
]


def base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def config_path() -> Path:
    return base_dir() / "business_waybill_raw_msg_service.json"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("business_waybill_raw_msg_service.json must be a JSON object")
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


def parse_time(value: Any) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:19], fmt)
        except ValueError:
            continue
    return None


def component_name(db_path: Path) -> str:
    normalized = str(db_path).lower()
    if "cnprinttool" in normalized:
        return "CNPrintTool"
    if "cloudprintclient" in normalized:
        return "CloudPrintClient"
    return db_path.parent.parent.name or "unknown"


def component_db_id(db_path: Path) -> str:
    return str(db_path).lower()


def data_dir() -> Path:
    path = base_dir() / "data" / "raw-msg-component-db-copies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_db(db_path: Path) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in component_name(db_path))
    copy_path = data_dir() / f"{safe}_latest_copy.db"
    shutil.copy2(db_path, copy_path)
    return copy_path


def component_status() -> list[dict[str, Any]]:
    rows = []
    for db_path in DEFAULT_DBS:
        exists = db_path.exists()
        stat = db_path.stat() if exists else None
        rows.append(
            {
                "name": component_name(db_path),
                "path": str(db_path),
                "exists": exists,
                "size": stat.st_size if stat else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat else "",
            }
        )
    return rows


def read_raw_task_rows(db_path: Path) -> list[dict[str, Any]]:
    if not db_path.exists():
        return []

    db_copy = copy_db(db_path)
    con = sqlite3.connect(db_copy)
    try:
        rows = con.execute("select rowid, taskID, msg, time from task order by rowid").fetchall()
    finally:
        con.close()

    result = []
    for rowid, task_id, msg, task_time in rows:
        result.append(
            {
                "task_id": "" if task_id is None else str(task_id),
                "task_time": "" if task_time is None else str(task_time),
                "raw_msg": "" if msg is None else str(msg),
                "component_name": component_name(db_path),
                "component_db_path": str(db_path),
                "component_db_id": component_db_id(db_path),
                "component_rowid": int(rowid or 0),
            }
        )
    return result


def collect_raw_task_rows() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for db_path in DEFAULT_DBS:
        rows.extend(read_raw_task_rows(db_path))
    return rows


def max_rowids(rows: list[dict[str, Any]]) -> dict[str, int]:
    result: dict[str, int] = {}
    for row in rows:
        db_id = str(row.get("component_db_id") or "")
        rowid = int(row.get("component_rowid") or 0)
        if db_id and rowid > 0:
            result[db_id] = max(result.get(db_id, 0), rowid)
    return result


def is_after_start(row: dict[str, Any], baseline_rowids: dict[str, int], started_at: datetime | None) -> bool:
    db_id = str(row.get("component_db_id") or "")
    rowid = int(row.get("component_rowid") or 0)
    if db_id in baseline_rowids:
        return rowid > baseline_rowids.get(db_id, 0)

    # If a component DB appears only after listening started, avoid uploading old rows.
    row_time = parse_time(row.get("task_time"))
    return bool(row_time and started_at and row_time >= started_at)


def upload_record(row: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "打印信息": "" if row.get("raw_msg") is None else str(row.get("raw_msg")),
        "task_id": str(row.get("task_id") or ""),
        "document_id": "",
        "task_time": str(row.get("task_time") or ""),
        "source_record_index": index,
        "extract_status": "原始msg未处理",
        "component_name": str(row.get("component_name") or ""),
        "component_db_path": str(row.get("component_db_path") or ""),
        "component_rowid": int(row.get("component_rowid") or 0),
    }


def log(message: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    log_dir = base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "business_waybill_raw_msg_service.log").open("a", encoding="utf-8") as file:
        file.write(line + "\n")


class RawMsgWaybillService:
    def __init__(self, cfg: dict[str, Any]) -> None:
        self.server_url = str(os.environ.get("ORDER_WAYBILL_SERVER_URL") or cfg.get("order_server_url") or "").strip().rstrip("/")
        self.poll_interval = max(1.0, float(cfg.get("poll_interval_seconds") or 2))
        self.machine_name = str(cfg.get("machine_name") or socket.gethostname()).strip() or socket.gethostname()
        self.machine_label = str(cfg.get("machine_label") or self.machine_name).strip() or self.machine_name
        self.client_id = f"rawmsg-{self.machine_name}-{getpass.getuser()}"
        self.active_batch_id = ""
        self.baseline_rowids: dict[str, int] = {}
        self.started_at: datetime | None = None
        self.uploaded_batches: set[str] = set()
        self.stop_event = threading.Event()
        self.last_error_text = ""
        self.last_error_log_at = 0.0

    def run(self) -> None:
        if not self.server_url:
            raise RuntimeError("order_server_url is empty in business_waybill_raw_msg_service.json")
        log(f"raw_msg_service_start server={self.server_url} machine={self.machine_label}")
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
                "components": component_status(),
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
        records = collect_raw_task_rows()
        self.active_batch_id = batch_id
        self.started_at = datetime.now()
        self.baseline_rowids = max_rowids(records)
        component_text = ",".join(f"{Path(db_id).name}:{rowid}" for db_id, rowid in sorted(self.baseline_rowids.items()))
        log(f"raw_msg_batch_start batch={batch_id} baseline={len(records)} components={component_text}")

    def stop_batch(self, batch_id: str) -> None:
        if batch_id in self.uploaded_batches:
            return
        if self.active_batch_id != batch_id:
            self.start_batch(batch_id)
        records = collect_raw_task_rows()
        batch_records = [row for row in records if is_after_start(row, self.baseline_rowids, self.started_at)]
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
                "records": [upload_record(row, index) for index, row in enumerate(batch_records, 1)],
                "records_found": len(batch_records),
                "records_scanned": len(records),
                "capture_mode": "raw_component_msg",
                "upload_mode": "component_rowid_after_listen_start_no_extraction",
            },
        )
        if response.get("ok"):
            self.uploaded_batches.add(batch_id)
            self.active_batch_id = ""
            self.started_at = None
            log(
                f"raw_msg_batch_uploaded batch={batch_id} records={len(batch_records)} "
                f"found={len(records)} mode=component_rowid_after_listen_start_no_extraction"
            )
        else:
            log(f"raw_msg_upload_rejected batch={batch_id} response={response}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Raw component msg waybill monitor service")
    parser.add_argument("--print-config", action="store_true", help="print the current config path and exit")
    args = parser.parse_args()
    if args.print_config:
        print(config_path())
        return
    service = RawMsgWaybillService(load_config())
    service.run()


if __name__ == "__main__":
    main()
