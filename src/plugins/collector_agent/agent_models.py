# -*- coding: utf-8 -*-
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


OFFICIAL_NAME = "打印组件信息采集"
INTERNAL_NAME = "OrderCollectorAgent"
AGENT_VERSION = "7.9.3"
PROTOCOL_VERSION = "collector.v1"
MIN_SUPPORTED_AGENT_VERSION = "7.9.3"
DEFAULT_SERVER_URL = "http://127.0.0.1:8000"
NO_PRINT_TEXT_PLACEHOLDER = "[未提取到打印文字，已保留原始打印任务]"

REQUIRED_RAW_RECORD_FIELDS = (
    "client_id",
    "machine_name",
    "machine_label",
    "agent_version",
    "protocol_version",
    "batch_id",
    "component_name",
    "component_db_id",
    "component_db_path",
    "component_rowid",
    "task_id",
    "document_id",
    "task_time",
    "source_record_index",
    "raw_msg_json",
    "raw_document_json",
    "print_text_raw",
    "extract_status",
    "created_at",
)


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def upload_dedupe_key(record: dict[str, Any]) -> tuple[str, str, str, str, str]:
    return (
        str(record.get("component_db_id") or ""),
        str(record.get("component_rowid") or ""),
        str(record.get("task_id") or ""),
        str(record.get("document_id") or ""),
        str(record.get("source_record_index") or ""),
    )


def ensure_required_fields(record: dict[str, Any]) -> dict[str, Any]:
    result = dict(record)
    for field in REQUIRED_RAW_RECORD_FIELDS:
        result.setdefault(field, "")
    result.setdefault("agent_version", AGENT_VERSION)
    result.setdefault("protocol_version", PROTOCOL_VERSION)
    result.setdefault("created_at", utc_now_text())
    result["print_text_raw"] = str(result.get("print_text_raw") or "").strip() or NO_PRINT_TEXT_PLACEHOLDER
    return result
