# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
from typing import Any

from .agent_config import cache_dir
from .agent_models import NO_PRINT_TEXT_PLACEHOLDER, utc_now_text


DEFAULT_DBS = (
    Path(r"C:\Program Files (x86)\CNPrintTool\resources\print.db"),
    Path(r"C:\Program Files (x86)\CloudPrintClient\resources\print.db"),
)


def compact_json(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def configured_db_paths() -> list[Path]:
    override = os.environ.get("ORDER_COLLECTOR_DB_PATHS", "").strip()
    if not override:
        return list(DEFAULT_DBS)
    parts = re.split(r"[;\n|]+", override)
    return [Path(part.strip().strip('"')) for part in parts if part.strip()]


def db_paths(existing_only: bool = True) -> list[Path]:
    paths = configured_db_paths()
    return [path for path in paths if path.exists()] if existing_only else paths


def component_name(db_path: Path) -> str:
    text = str(db_path).lower()
    if "cnprinttool" in text:
        return "CNPrintTool"
    if "cloudprintclient" in text:
        return "CloudPrintClient"
    return db_path.parent.parent.name or db_path.parent.name or "UnknownPrintComponent"


def component_db_id(db_path: Path) -> str:
    return str(db_path).lower()


def safe_copy_name(db_path: Path) -> str:
    digest = hashlib.sha1(str(db_path).lower().encode("utf-8", errors="ignore")).hexdigest()[:10]
    safe_name = re.sub(r"[^A-Za-z0-9_.-]+", "_", component_name(db_path)).strip("_") or "print_component"
    return f"{safe_name}_{digest}.db"


def copy_db(db_path: Path) -> Path:
    target = cache_dir() / safe_copy_name(db_path)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(db_path, target)
    return target


def qname(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def table_columns(con: sqlite3.Connection, table: str) -> set[str]:
    try:
        rows = con.execute(f"pragma table_info({qname(table)})").fetchall()
    except sqlite3.DatabaseError:
        return set()
    return {str(row[1]) for row in rows}


def choose_column(columns: set[str], names: tuple[str, ...]) -> str | None:
    lowered = {name.lower(): name for name in columns}
    for name in names:
        match = lowered.get(name.lower())
        if match:
            return match
    return None


def select_task_rows(db_copy: Path, after_rowid: int = 0, through_rowid: int | None = None) -> list[dict[str, Any]]:
    con = sqlite3.connect(db_copy)
    con.row_factory = sqlite3.Row
    try:
        columns = table_columns(con, "task")
        if not columns:
            return []
        task_col = choose_column(columns, ("taskID", "task_id", "taskId", "id"))
        msg_col = choose_column(columns, ("msg", "message", "payload", "raw_msg"))
        time_col = choose_column(columns, ("time", "created_at", "createTime", "task_time"))
        if not msg_col:
            return []
        selected = [
            "rowid as component_rowid",
            f"{qname(task_col)} as task_id" if task_col else "'' as task_id",
            f"{qname(msg_col)} as msg",
            f"{qname(time_col)} as task_time" if time_col else "'' as task_time",
        ]
        params: list[Any] = [int(after_rowid or 0)]
        where = "rowid > ?"
        if through_rowid is not None:
            where += " and rowid <= ?"
            params.append(int(through_rowid))
        sql = f"select {', '.join(selected)} from task where {where} order by rowid"
        return [dict(row) for row in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def max_task_rowid(db_path: Path) -> int:
    if not db_path.exists():
        return 0
    try:
        db_copy = copy_db(db_path)
        con = sqlite3.connect(db_copy)
        try:
            row = con.execute("select max(rowid) from task").fetchone()
            return int(row[0] or 0) if row else 0
        finally:
            con.close()
    except (OSError, sqlite3.DatabaseError, ValueError):
        return 0


def current_max_rowids() -> dict[str, int]:
    return {component_db_id(path): max_task_rowid(path) for path in db_paths(existing_only=True)}


def component_status() -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for db_path in db_paths(existing_only=False):
        exists = db_path.exists()
        stat = db_path.stat() if exists else None
        rows.append(
            {
                "name": component_name(db_path),
                "component_name": component_name(db_path),
                "path": str(db_path),
                "component_db_id": component_db_id(db_path),
                "exists": exists,
                "size": int(stat.st_size) if stat else 0,
                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S") if stat else "",
                "max_rowid": max_task_rowid(db_path) if exists else 0,
            }
        )
    return rows


def iter_text_nodes(print_xml: str) -> tuple[list[str], bool]:
    text = str(print_xml or "")
    if not text:
        return [], False
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        cdata = [item.strip() for item in re.findall(r"<!\[CDATA\[(.*?)\]\]>", text, flags=re.S) if item.strip()]
        return cdata, True
    chunks: list[str] = []
    for elem in root.iter():
        tag = str(elem.tag).split("}")[-1].lower()
        if tag.endswith("text"):
            value = "".join(elem.itertext()).strip()
            if value and value != "\u3000":
                chunks.append(value)
    return chunks, False


def normalize_print_text(chunks: list[str]) -> str:
    text = "\n".join([str(chunk or "").strip() for chunk in chunks if str(chunk or "").strip()])
    text = text.replace("\u3000", " ").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_documents(payload: object) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    task = payload.get("task") if isinstance(payload.get("task"), dict) else payload
    documents = task.get("documents") if isinstance(task, dict) else None
    if documents is None:
        documents = payload.get("documents")
    if isinstance(documents, list):
        return [item for item in documents if isinstance(item, dict)]
    if isinstance(documents, dict):
        return [documents]
    return []


def payload_task_id(payload: object) -> str:
    if not isinstance(payload, dict):
        return ""
    task = payload.get("task") if isinstance(payload.get("task"), dict) else payload
    for source in (task, payload):
        if isinstance(source, dict):
            for key in ("taskID", "taskId", "task_id", "id"):
                value = source.get(key)
                if value not in (None, ""):
                    return str(value)
    return ""


def document_id(document: dict[str, Any], index: int) -> str:
    for key in ("documentID", "documentId", "document_id", "id"):
        value = document.get(key)
        if value not in (None, ""):
            return str(value)
    return str(index)


def document_print_text(document: dict[str, Any]) -> tuple[str, str]:
    contents = document.get("contents")
    if not isinstance(contents, list):
        contents = []
    chunks: list[str] = []
    xml_failed = False
    for content in contents:
        if not isinstance(content, dict):
            continue
        extracted, failed = iter_text_nodes(str(content.get("printXML") or ""))
        chunks.extend(extracted)
        xml_failed = xml_failed or failed
    text = normalize_print_text(chunks)
    if xml_failed:
        return text or NO_PRINT_TEXT_PLACEHOLDER, "print_xml_parse_failed"
    if not text:
        return NO_PRINT_TEXT_PLACEHOLDER, "empty_print_text"
    return text, "raw_preserved"


def record_source_fields(db_path: Path, row: dict[str, Any], batch_id: str) -> dict[str, Any]:
    return {
        "batch_id": batch_id,
        "component_name": component_name(db_path),
        "component_db_id": component_db_id(db_path),
        "component_db_path": str(db_path),
        "component_rowid": row.get("component_rowid"),
        "task_id": str(row.get("task_id") or ""),
        "task_time": str(row.get("task_time") or ""),
        "created_at": utc_now_text(),
    }


def fallback_record(
    db_path: Path,
    row: dict[str, Any],
    batch_id: str,
    raw_msg_json: str,
    raw_document_json: str,
    print_text_raw: str,
    extract_status: str,
    source_record_index: int = 1,
) -> dict[str, Any]:
    return {
        **record_source_fields(db_path, row, batch_id),
        "document_id": "",
        "source_record_index": source_record_index,
        "raw_msg_json": raw_msg_json,
        "raw_document_json": raw_document_json,
        "print_text_raw": print_text_raw or NO_PRINT_TEXT_PLACEHOLDER,
        "extract_status": extract_status,
    }


def extract_records_from_row(db_path: Path, row: dict[str, Any], batch_id: str) -> list[dict[str, Any]]:
    raw_msg = row.get("msg")
    raw_msg_json = str(raw_msg or "")
    try:
        payload = json.loads(raw_msg_json)
    except (TypeError, json.JSONDecodeError):
        return [
            fallback_record(
                db_path,
                row,
                batch_id,
                raw_msg_json=raw_msg_json,
                raw_document_json="",
                print_text_raw=raw_msg_json or NO_PRINT_TEXT_PLACEHOLDER,
                extract_status="raw_json_parse_failed",
            )
        ]

    raw_msg_json = compact_json(payload)
    if not row.get("task_id"):
        task_id = payload_task_id(payload)
        if task_id:
            row = dict(row)
            row["task_id"] = task_id
    documents = extract_documents(payload)
    if not documents:
        return [
            fallback_record(
                db_path,
                row,
                batch_id,
                raw_msg_json=raw_msg_json,
                raw_document_json=compact_json(payload),
                print_text_raw=NO_PRINT_TEXT_PLACEHOLDER,
                extract_status="no_documents",
            )
        ]

    records: list[dict[str, Any]] = []
    for index, document in enumerate(documents, 1):
        print_text_raw, extract_status = document_print_text(document)
        records.append(
            {
                **record_source_fields(db_path, row, batch_id),
                "document_id": document_id(document, index),
                "source_record_index": index,
                "raw_msg_json": raw_msg_json,
                "raw_document_json": compact_json(document),
                "print_text_raw": print_text_raw or NO_PRINT_TEXT_PLACEHOLDER,
                "extract_status": extract_status,
            }
        )
    return records


def extract_records(db_path: Path, after_rowid: int = 0, through_rowid: int | None = None, batch_id: str = "") -> list[dict[str, Any]]:
    if not db_path.exists():
        return []
    db_copy = copy_db(db_path)
    rows = select_task_rows(db_copy, after_rowid=after_rowid, through_rowid=through_rowid)
    records: list[dict[str, Any]] = []
    for row in rows:
        produced = extract_records_from_row(db_path, row, batch_id=batch_id)
        records.extend(produced or [fallback_record(db_path, row, batch_id, "", "", NO_PRINT_TEXT_PLACEHOLDER, "empty_task_row")])
    return records


def collect_records(
    start_rowids: dict[str, int] | None = None,
    stop_rowids: dict[str, int] | None = None,
    batch_id: str = "",
) -> list[dict[str, Any]]:
    start_rowids = start_rowids or {}
    stop_rowids = stop_rowids or {}
    records: list[dict[str, Any]] = []
    for db_path in db_paths(existing_only=True):
        db_id = component_db_id(db_path)
        records.extend(
            extract_records(
                db_path,
                after_rowid=int(start_rowids.get(db_id) or 0),
                through_rowid=stop_rowids.get(db_id),
                batch_id=batch_id,
            )
        )
    return records
