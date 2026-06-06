# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core.collector_config import validate_collection_mode
from core.waybill_files import raw_record_text, record_key
from core.waybill_text_parser import MODE_UNKNOWN, PARSE_STATUS_FIELD, detect_waybill_mode, parse_waybill_raw_text
from utils.order_secure_common import get_data_dir


RAW_RECORDS_FILENAME = "collector_raw_records.jsonl"
RAW_RECORD_SNIPPET_LENGTH = 180


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def raw_records_dir() -> Path:
    path = Path(get_data_dir()) / "waybill-monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def raw_records_path() -> Path:
    return raw_records_dir() / RAW_RECORDS_FILENAME


def compact_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    except TypeError:
        return json.dumps(str(value), ensure_ascii=False)


def raw_payload_text(record: dict[str, Any]) -> str:
    value = record.get("raw_payload_json")
    if value:
        return str(value)
    return compact_json(record)


def normalized_raw_text(record: dict[str, Any]) -> str:
    return str(record.get("raw_print_text") or raw_record_text(record) or "").strip()


def raw_hash(raw_text: str, payload_json: str) -> str:
    source = raw_text if raw_text else payload_json
    return hashlib.sha256(source.encode("utf-8", errors="ignore")).hexdigest()


def parse_record_summary(raw_text: str, rule_config: object | None = None) -> dict[str, Any]:
    if not raw_text:
        return {"parse_status": "empty", "pattern_type": ""}
    pattern = detect_waybill_mode(raw_text)
    parsed_rows = parse_waybill_raw_text(raw_text, "", rule_config)
    if not parsed_rows:
        return {"parse_status": "unparsed", "pattern_type": pattern if pattern != MODE_UNKNOWN else ""}
    first = parsed_rows[0]
    return {
        "parse_status": str(first.get(PARSE_STATUS_FIELD) or "parsed"),
        "pattern_type": str(first.get("面单模式") or pattern or ""),
        "parsed_count": len(parsed_rows),
    }


def build_raw_record(
    record: dict[str, Any],
    collection_mode: str,
    collector_id: str = "",
    batch_id: str = "",
    collector_version: str = "",
    rule_config: object | None = None,
) -> dict[str, Any]:
    mode = validate_collection_mode(collection_mode)
    raw_text = normalized_raw_text(record)
    payload_json = raw_payload_text(record)
    digest = raw_hash(raw_text, payload_json)
    parse_info = parse_record_summary(raw_text, rule_config)
    now = utc_now_text()
    source_key = record_key(record)
    return {
        "record_id": uuid.uuid4().hex,
        "collection_mode": mode,
        "raw_print_text": raw_text,
        "raw_payload_json": payload_json,
        "raw_hash": digest,
        "pattern_type": str(record.get("pattern_type") or parse_info.get("pattern_type") or ""),
        "parse_status": str(record.get("parse_status") or parse_info.get("parse_status") or ""),
        "parsed_count": int(parse_info.get("parsed_count") or 0),
        "collector_version": str(collector_version or record.get("collector_version") or ""),
        "collector_id": str(collector_id or record.get("source_client_id") or ""),
        "batch_id": str(batch_id or record.get("batch_id") or ""),
        "task_id": str(record.get("task_id") or ""),
        "document_id": str(record.get("document_id") or ""),
        "task_time": str(record.get("task_time") or ""),
        "source_record_index": str(record.get("source_record_index") or record.get("record_index") or ""),
        "machine_name": str(record.get("machine_name") or ""),
        "machine_label": str(record.get("machine_label") or ""),
        "extract_status": str(record.get("extract_status") or ""),
        "source_key": source_key,
        "created_at": now,
        "updated_at": now,
    }


def append_raw_records(
    records: list[dict[str, Any]],
    collection_mode: str,
    collector_id: str = "",
    batch_id: str = "",
    collector_version: str = "",
    rule_config: object | None = None,
) -> list[dict[str, Any]]:
    if not records:
        return []
    path = raw_records_path()
    rows = [
        build_raw_record(
            record,
            collection_mode=collection_mode,
            collector_id=collector_id,
            batch_id=batch_id,
            collector_version=collector_version,
            rule_config=rule_config,
        )
        for record in records
    ]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")
    return rows


def iter_raw_records(limit: int | None = None) -> list[dict[str, Any]]:
    path = raw_records_path()
    if not path.exists():
        return []
    rows: list[dict[str, Any]] | deque[dict[str, Any]]
    rows = deque(maxlen=limit) if limit else []
    with path.open("r", encoding="utf-8", errors="ignore") as file:
        for line in file:
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if isinstance(row, dict):
                rows.append(row)
    return list(rows)


def public_raw_record(row: dict[str, Any], include_text: bool = False) -> dict[str, Any]:
    raw_text = str(row.get("raw_print_text") or "")
    payload = {
        "record_id": row.get("record_id", ""),
        "collection_mode": row.get("collection_mode", ""),
        "parse_status": row.get("parse_status", ""),
        "pattern_type": row.get("pattern_type", ""),
        "raw_hash": row.get("raw_hash", ""),
        "raw_preview": raw_text[:RAW_RECORD_SNIPPET_LENGTH],
        "raw_length": len(raw_text),
        "collector_id": row.get("collector_id", ""),
        "collector_version": row.get("collector_version", ""),
        "batch_id": row.get("batch_id", ""),
        "task_id": row.get("task_id", ""),
        "document_id": row.get("document_id", ""),
        "machine_label": row.get("machine_label", ""),
        "source_record_index": row.get("source_record_index", ""),
        "created_at": row.get("created_at", ""),
    }
    if include_text:
        payload["raw_print_text"] = raw_text
        payload["raw_payload_json"] = row.get("raw_payload_json", "")
    return payload


def list_raw_records(limit: int = 50, include_text: bool = False) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    rows = iter_raw_records(limit=limit)
    return [public_raw_record(row, include_text=include_text) for row in reversed(rows)]


def get_raw_record(record_id: str) -> dict[str, Any] | None:
    target = str(record_id or "").strip()
    if not target:
        return None
    for row in reversed(iter_raw_records()):
        if str(row.get("record_id") or "") == target:
            return public_raw_record(row, include_text=True)
    return None
