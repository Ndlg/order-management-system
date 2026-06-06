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
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Any
import urllib.request


SOURCE_ROOT = Path(__file__).resolve().parents[1]
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import waybill_collector_reader
from waybill_files import record_key


TOOL_VERSION = "business_collector_v2_20260605"
CAPTURE_MODES = {
    "raw_full": "原始全量采集",
    "filtered": "规则过滤采集",
}
DEFAULT_CONFIG = {
    "order_server_url": "http://127.0.0.1:8000",
    "poll_interval_seconds": 2,
    "machine_name": "",
    "machine_label": "",
    "default_capture_mode": "raw_full",
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
    return base_dir() / "business_waybill_collector_v2.json"


def normalize_capture_mode(value: Any) -> str:
    text = str(value or "").strip()
    aliases = {
        "raw": "raw_full",
        "raw_msg": "raw_full",
        "raw_component_msg": "raw_full",
        "原始": "raw_full",
        "原始全量": "raw_full",
        "原始全量采集": "raw_full",
        "filter": "filtered",
        "filtered": "filtered",
        "规则": "filtered",
        "规则过滤": "filtered",
        "规则过滤采集": "filtered",
    }
    mode = aliases.get(text, text)
    return mode if mode in CAPTURE_MODES else "raw_full"


def load_config() -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        path.write_text(json.dumps(DEFAULT_CONFIG, ensure_ascii=False, indent=2), encoding="utf-8")
        return dict(DEFAULT_CONFIG)
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise RuntimeError("business_waybill_collector_v2.json must be a JSON object")
    merged = dict(DEFAULT_CONFIG)
    merged.update(data)
    merged["default_capture_mode"] = normalize_capture_mode(merged.get("default_capture_mode"))
    return merged


def save_config(cfg: dict[str, Any]) -> None:
    config_path().write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")


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


def data_dir() -> Path:
    path = base_dir() / "data" / "business-v2-component-db-copies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def copy_db(db_path: Path) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "._-" else "_" for ch in component_name(db_path))
    copy_path = data_dir() / f"{safe}_latest_copy.db"
    shutil.copy2(db_path, copy_path)
    return copy_path


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
        db_id = str(row.get("component_db_id") or "").strip().lower()
        try:
            rowid = int(row.get("component_rowid") or 0)
        except (TypeError, ValueError):
            rowid = 0
        if db_id and rowid > 0:
            result[db_id] = max(result.get(db_id, 0), rowid)
    return result


def component_db_key(row: dict[str, Any]) -> str:
    return str(row.get("component_db_id") or row.get("component_db_path") or "").strip().lower()


def component_rowid(row: dict[str, Any]) -> int:
    try:
        return int(row.get("component_rowid") or 0)
    except (TypeError, ValueError):
        return 0


def is_after_start(row: dict[str, Any], baseline_rowids: dict[str, int], started_at: datetime | None) -> bool:
    db_id = component_db_key(row)
    rowid = component_rowid(row)
    if db_id in baseline_rowids:
        return rowid > baseline_rowids.get(db_id, 0)
    row_time = parse_time(row.get("task_time"))
    return bool(row_time and started_at and row_time >= started_at)


def raw_upload_record(row: dict[str, Any], index: int) -> dict[str, Any]:
    return {
        "打印信息": "" if row.get("raw_msg") is None else str(row.get("raw_msg")),
        "task_id": str(row.get("task_id") or ""),
        "document_id": "",
        "task_time": str(row.get("task_time") or ""),
        "source_record_index": index,
        "extract_status": "原始msg未处理",
        "component_name": str(row.get("component_name") or ""),
        "component_db_path": str(row.get("component_db_path") or ""),
        "component_rowid": component_rowid(row),
    }


def filtered_upload_record(row: dict[str, Any], index: int) -> dict[str, Any]:
    raw_text = str(row.get("打印信息") or row.get("print_text_raw") or row.get("print_text") or "").strip()
    if not raw_text:
        raw_text = "[无打印信息]"
    return {
        "打印信息": raw_text,
        "task_id": str(row.get("task_id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "task_time": str(row.get("task_time") or ""),
        "source_record_index": index,
        "extract_status": str(row.get("extract_status") or ""),
        "component_name": str(row.get("component_name") or ""),
        "component_db_path": str(row.get("component_db_path") or ""),
        "component_rowid": component_rowid(row),
    }


def normalize_capture_rules(value: Any) -> dict[str, list[str]]:
    if not isinstance(value, dict):
        value = {}
    result = {"include_keywords": [], "exclude_keywords": []}
    for key in result:
        raw = value.get(key, [])
        if isinstance(raw, str):
            raw = raw.replace("\n", "/").replace("，", ",").replace("、", ",").replace("；", ",").replace(";", ",").split(",")
        if not isinstance(raw, list):
            raw = []
        seen = set()
        for item in raw:
            for part in str(item or "").replace("\n", "/").split("/"):
                text = part.strip()
                if text and text not in seen:
                    seen.add(text)
                    result[key].append(text)
    return result


def record_search_text(row: dict[str, Any]) -> str:
    parts = [
        row.get("打印信息"),
        row.get("print_text_raw"),
        row.get("print_text"),
        row.get("raw_msg"),
        row.get("task_id"),
        row.get("document_id"),
        row.get("task_time"),
    ]
    return "\n".join(str(part or "") for part in parts).casefold()


def passes_capture_rules(row: dict[str, Any], rules: dict[str, list[str]]) -> bool:
    text = record_search_text(row)
    include_keywords = [item.casefold() for item in rules.get("include_keywords", []) if item]
    exclude_keywords = [item.casefold() for item in rules.get("exclude_keywords", []) if item]
    if include_keywords and not any(keyword in text for keyword in include_keywords):
        return False
    if exclude_keywords and any(keyword in text for keyword in exclude_keywords):
        return False
    return True


def log(message: str) -> None:
    line = f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')} {message}"
    print(line, flush=True)
    log_dir = base_dir() / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    with (log_dir / "business_waybill_collector_v2.log").open("a", encoding="utf-8") as file:
        file.write(line + "\n")


class BusinessCollectorV2:
    def __init__(self, cfg: dict[str, Any], status_callback=None) -> None:
        self.status_callback = status_callback
        self.cfg = dict(cfg)
        self.server_url = ""
        self.poll_interval = 2.0
        self.machine_name = ""
        self.machine_label = ""
        self.client_id = ""
        self.default_capture_mode = "raw_full"
        self.active_capture_mode = ""
        self.active_batch_id = ""
        self.capture_rules = normalize_capture_rules({})
        self.baseline_rowids: dict[str, int] = {}
        self.started_at: datetime | None = None
        self.uploaded_batches: set[str] = set()
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None
        self.last_error_text = ""
        self.last_error_log_at = 0.0
        self.reload_config(cfg)

    def reload_config(self, cfg: dict[str, Any]) -> None:
        self.cfg = dict(cfg)
        self.server_url = str(os.environ.get("ORDER_WAYBILL_SERVER_URL") or cfg.get("order_server_url") or "").strip().rstrip("/")
        self.poll_interval = max(1.0, float(cfg.get("poll_interval_seconds") or 2))
        self.machine_name = str(cfg.get("machine_name") or socket.gethostname()).strip() or socket.gethostname()
        self.machine_label = str(cfg.get("machine_label") or self.machine_name).strip() or self.machine_name
        self.default_capture_mode = normalize_capture_mode(cfg.get("default_capture_mode"))
        self.client_id = f"business-v2-{self.machine_name}-{getpass.getuser()}"

    def start_background(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def stop_background(self) -> None:
        self.stop_event.set()

    def emit_status(self, message: str) -> None:
        if self.status_callback:
            self.status_callback(message)

    def run(self) -> None:
        if not self.server_url:
            raise RuntimeError("order_server_url is empty")
        log(f"collector_v2_start server={self.server_url} machine={self.machine_label} default_mode={self.default_capture_mode}")
        self.emit_status("后台心跳已启用")
        while not self.stop_event.is_set():
            try:
                self.tick()
            except Exception as exc:
                self.log_connect_wait(exc)
            self.stop_event.wait(self.poll_interval)
        log("collector_v2_stop")
        self.emit_status("后台心跳已停止")

    def log_connect_wait(self, exc: Exception) -> None:
        text = str(exc)
        now = time.time()
        if text == self.last_error_text and now - self.last_error_log_at < 30:
            return
        self.last_error_text = text
        self.last_error_log_at = now
        log(f"waiting_order_server server={self.server_url} reason={text}")
        self.emit_status(f"等待连接服务端：{text}")

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
                "tool_version": TOOL_VERSION,
                "active_batch_id": self.active_batch_id,
                "preferred_capture_mode": self.default_capture_mode,
                "active_capture_mode": self.active_capture_mode or self.default_capture_mode,
                "components": component_status(),
            },
        )
        if not response.get("ok"):
            log(f"poll_rejected {response}")
            return
        command = str(response.get("command") or "idle").lower()
        batch_id = str(response.get("batch_id") or "")
        self.capture_rules = normalize_capture_rules(response.get("capture_rules"))
        if command == "start" and batch_id:
            self.start_batch(batch_id, response.get("capture_mode"))
        elif command == "stop" and batch_id:
            self.stop_batch(batch_id)
        else:
            self.emit_status(f"已连接：{response.get('status', 'idle')}，默认模式 {CAPTURE_MODES[self.default_capture_mode]}")

    def start_batch(self, batch_id: str, capture_mode: Any) -> None:
        if self.active_batch_id == batch_id:
            return
        rows = collect_raw_task_rows()
        self.active_batch_id = batch_id
        self.active_capture_mode = normalize_capture_mode(capture_mode or self.default_capture_mode)
        self.started_at = datetime.now()
        self.baseline_rowids = max_rowids(rows)
        component_text = ",".join(f"{Path(db_id).name}:{rowid}" for db_id, rowid in sorted(self.baseline_rowids.items()))
        log(
            f"batch_start batch={batch_id} baseline={len(rows)} mode={self.active_capture_mode} "
            f"include={len(self.capture_rules.get('include_keywords', []))} exclude={len(self.capture_rules.get('exclude_keywords', []))} "
            f"components={component_text}"
        )
        self.emit_status(f"监听已开始：{CAPTURE_MODES[self.active_capture_mode]}")

    def stop_batch(self, batch_id: str) -> None:
        if batch_id in self.uploaded_batches:
            return
        if self.active_batch_id != batch_id:
            self.start_batch(batch_id, self.default_capture_mode)

        if self.active_capture_mode == "filtered":
            all_records = waybill_collector_reader.collect_records()
            window_records = [row for row in all_records if is_after_start(row, self.baseline_rowids, self.started_at)]
            batch_records = [row for row in window_records if passes_capture_rules(row, self.capture_rules)]
            upload_records = [filtered_upload_record(row, index) for index, row in enumerate(batch_records, 1)]
            upload_mode = "component_rowid_after_listen_start_filtered_by_server_rules"
        else:
            all_records = collect_raw_task_rows()
            window_records = [row for row in all_records if is_after_start(row, self.baseline_rowids, self.started_at)]
            batch_records = window_records
            upload_records = [raw_upload_record(row, index) for index, row in enumerate(batch_records, 1)]
            upload_mode = "component_rowid_after_listen_start_raw_msg_no_extraction"

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
                "records": upload_records,
                "records_found": len(batch_records),
                "records_scanned": len(all_records),
                "capture_mode": self.active_capture_mode,
                "capture_mode_source": "server_batch",
                "upload_mode": upload_mode,
            },
        )
        if response.get("ok"):
            self.uploaded_batches.add(batch_id)
            log(
                f"batch_uploaded batch={batch_id} records={len(batch_records)} scanned={len(all_records)} "
                f"mode={self.active_capture_mode} upload_mode={upload_mode}"
            )
            self.emit_status(f"已上传：{len(batch_records)} 条，模式 {CAPTURE_MODES[self.active_capture_mode]}")
            self.active_batch_id = ""
            self.active_capture_mode = ""
            self.started_at = None
        else:
            log(f"upload_rejected batch={batch_id} response={response}")
            self.emit_status(f"上传被拒绝：{response}")


class CollectorWindow:
    def __init__(self) -> None:
        self.root = tk.Tk()
        self.root.title("业务机面单采集工具 V2")
        self.root.geometry("680x500")
        self.cfg = load_config()
        self.collector: BusinessCollectorV2 | None = None
        self.status_var = tk.StringVar(value="未启用")
        self.server_var = tk.StringVar(value=str(self.cfg.get("order_server_url") or ""))
        self.machine_label_var = tk.StringVar(value=str(self.cfg.get("machine_label") or socket.gethostname()))
        self.machine_name_var = tk.StringVar(value=str(self.cfg.get("machine_name") or socket.gethostname()))
        self.mode_var = tk.StringVar(value=normalize_capture_mode(self.cfg.get("default_capture_mode")))
        self.build()

    def build(self) -> None:
        outer = ttk.Frame(self.root, padding=16)
        outer.pack(fill="both", expand=True)

        title = ttk.Label(outer, text="业务机面单采集工具 V2", font=("Microsoft YaHei", 16, "bold"))
        title.pack(anchor="w")
        sub = ttk.Label(outer, text="启用后持续心跳到 8000 服务端；采集范围由前端开始/结束监听控制。")
        sub.pack(anchor="w", pady=(4, 16))

        form = ttk.Frame(outer)
        form.pack(fill="x")
        self.add_row(form, 0, "服务端 URL", ttk.Entry(form, textvariable=self.server_var))
        self.add_row(form, 1, "计算机名称", ttk.Entry(form, textvariable=self.machine_name_var))
        self.add_row(form, 2, "页面显示名", ttk.Entry(form, textvariable=self.machine_label_var))
        mode_combo = ttk.Combobox(
            form,
            textvariable=self.mode_var,
            state="readonly",
            values=list(CAPTURE_MODES.keys()),
        )
        self.add_row(form, 3, "本地默认模式", mode_combo)
        mode_label = ttk.Label(form, text="raw_full=原始全量，filtered=规则过滤；前端开始监听下发模式时以前端为准。")
        mode_label.grid(row=4, column=1, sticky="w", pady=(0, 10))
        form.columnconfigure(1, weight=1)

        actions = ttk.Frame(outer)
        actions.pack(fill="x", pady=(8, 12))
        ttk.Button(actions, text="保存配置", command=self.save).pack(side="left", padx=(0, 8))
        self.enable_btn = ttk.Button(actions, text="启用后台心跳", command=self.enable)
        self.enable_btn.pack(side="left", padx=(0, 8))
        self.stop_btn = ttk.Button(actions, text="停止心跳", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="打开日志目录", command=self.open_logs).pack(side="left")

        status_frame = ttk.LabelFrame(outer, text="运行状态", padding=12)
        status_frame.pack(fill="x", pady=(4, 12))
        ttk.Label(status_frame, textvariable=self.status_var, foreground="#0f766e").pack(anchor="w")

        notes = tk.Text(outer, height=10, wrap="word")
        notes.insert(
            "1.0",
            "说明：\n"
            "1. 工具启动后不会自动采集历史订单，只负责心跳和等待服务端命令。\n"
            "2. 前端页面点击开始监听时，工具记录当前组件数据库 rowid 基准。\n"
            "3. 前端页面点击结束监听时，工具只上传监听期间新增的打印记录。\n"
            "4. 原始全量采集会上传组件 task.msg 原文；规则过滤采集会先提取打印文字，并按系统 App 中维护的采集规则过滤。\n"
            "5. 不要和旧业务机采集工具同时采同一批，避免服务端收到重复数据。\n",
        )
        notes.configure(state="disabled")
        notes.pack(fill="both", expand=True)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def add_row(self, parent, row: int, label: str, widget) -> None:
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=6)
        widget.grid(row=row, column=1, sticky="ew", pady=6)

    def current_config(self) -> dict[str, Any]:
        return {
            "order_server_url": self.server_var.get().strip(),
            "poll_interval_seconds": 2,
            "machine_name": self.machine_name_var.get().strip() or socket.gethostname(),
            "machine_label": self.machine_label_var.get().strip() or self.machine_name_var.get().strip() or socket.gethostname(),
            "default_capture_mode": normalize_capture_mode(self.mode_var.get()),
        }

    def save(self) -> None:
        self.cfg = self.current_config()
        save_config(self.cfg)
        self.status_var.set(f"配置已保存：{config_path()}")
        if self.collector:
            self.collector.reload_config(self.cfg)

    def enable(self) -> None:
        self.save()
        self.collector = BusinessCollectorV2(self.cfg, self.thread_status)
        self.collector.start_background()
        self.enable_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status_var.set("后台心跳启动中...")

    def stop(self) -> None:
        if self.collector:
            self.collector.stop_background()
        self.enable_btn.configure(state="normal")
        self.stop_btn.configure(state="disabled")
        self.status_var.set("正在停止后台心跳...")

    def thread_status(self, message: str) -> None:
        self.root.after(0, lambda: self.status_var.set(message))

    def open_logs(self) -> None:
        log_dir = base_dir() / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        os.startfile(str(log_dir))

    def on_close(self) -> None:
        if self.collector and self.collector.thread and self.collector.thread.is_alive():
            if messagebox.askyesno("后台心跳正在运行", "关闭窗口会停止业务机采集心跳，确定关闭吗？"):
                self.collector.stop_background()
                self.root.destroy()
            return
        self.root.destroy()

    def run(self) -> None:
        self.root.mainloop()


def main() -> None:
    parser = argparse.ArgumentParser(description="Business waybill collector V2")
    parser.add_argument("--service", action="store_true", help="run heartbeat service without GUI")
    parser.add_argument("--print-config", action="store_true", help="print the current config path and exit")
    args = parser.parse_args()
    if args.print_config:
        print(config_path())
        return
    cfg = load_config()
    if args.service:
        service = BusinessCollectorV2(cfg)
        service.run()
        return
    CollectorWindow().run()


if __name__ == "__main__":
    main()
