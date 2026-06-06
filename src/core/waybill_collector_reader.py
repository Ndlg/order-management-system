# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from utils.order_secure_common import get_data_dir
from core.waybill_files import export_records


DEFAULT_DBS = [
    Path(r"C:\Program Files (x86)\CNPrintTool\resources\print.db"),
    Path(r"C:\Program Files (x86)\CloudPrintClient\resources\print.db"),
]


def get_waybill_data_dir() -> Path:
    path = Path(get_data_dir()) / "waybill-monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_component_copy_dir() -> Path:
    path = get_waybill_data_dir() / "component-db-copies"
    path.mkdir(parents=True, exist_ok=True)
    return path


def component_name(db_path: Path) -> str:
    normalized = str(db_path).lower()
    if "cnprinttool" in normalized:
        return "CNPrintTool"
    if "cloudprintclient" in normalized:
        return "CloudPrintClient"
    return db_path.parent.parent.name or "unknown"


def component_db_id(db_path: Path) -> str:
    return str(db_path).lower()


def component_status() -> list[dict]:
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


def db_paths() -> list[Path]:
    return [path for path in DEFAULT_DBS if path.exists()]


def copy_db(db_path: Path) -> Path:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", component_name(db_path))
    copy_path = get_component_copy_dir() / f"{safe}_latest_copy.db"
    shutil.copy2(db_path, copy_path)
    return copy_path


def iter_text_nodes(print_xml: str) -> list[str]:
    if not print_xml:
        return []
    try:
        root = ET.fromstring(print_xml)
    except ET.ParseError:
        return re.findall(r"<!\[CDATA\[(.*?)\]\]>", print_xml, flags=re.S)

    texts = []
    for elem in root.iter():
        if elem.tag.endswith("text"):
            value = "".join(elem.itertext()).strip()
            if value and value != "\u3000":
                texts.append(value)
    return texts


def normalize_print_text(text: str) -> str:
    text = str(text or "").replace("\u3000", " ").replace("\r", "\n")
    text = re.sub(r"[\uFF0C\u3001;\uFF1B]+", ",", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r",+", ",", text)
    return text.strip(" ,\n")


def choose_product_text(data: dict) -> str:
    for key in ("productInfo", "productShortInfo", "allProductInfo", "sPInfo", "sPSInfo"):
        value = data.get(key)
        if value:
            return str(value).strip()
    return ""


def compact_json(value: object) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def append_unique(lines: list[str], value: object) -> None:
    text = str(value or "").strip()
    if text and text not in lines:
        lines.append(text)


def data_text_lines(data: dict) -> list[str]:
    lines: list[str] = []
    known_keys = ("productInfo", "productShortInfo", "allProductInfo", "sPInfo", "sPSInfo")
    product_text = choose_product_text(data)
    append_unique(lines, product_text)

    for key, value in data.items():
        if key in known_keys or value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            text = compact_json(value)
        else:
            text = str(value).strip()
        append_unique(lines, f"{key}: {text}")
    return lines


def raw_document_text(task_id: object, document_id: object, document: dict) -> str:
    return "\n".join(
        [
            "[未提取到打印文字，已保留原始打印任务]",
            f"任务ID: {task_id or ''}",
            f"文档ID: {document_id or ''}",
            compact_json(document),
        ]
    )


def record_source_fields(db_path: Path, rowid: object) -> dict:
    return {
        "component_name": component_name(db_path),
        "component_db_path": str(db_path),
        "component_db_id": component_db_id(db_path),
        "component_rowid": rowid,
    }


def build_preserved_record(
    task_time: object,
    task_id: object,
    document_id: object,
    raw_text: object,
    status: str,
    db_path: Path,
    rowid: object,
) -> dict:
    raw_print_text = str(raw_text or "").strip() or "[无打印信息]"
    print_text = normalize_print_text(raw_print_text) or raw_print_text
    return {
        "task_time": task_time,
        "task_id": task_id,
        "document_id": document_id,
        "print_text": print_text,
        "print_text_raw": raw_print_text,
        "extract_status": status,
        **record_source_fields(db_path, rowid),
    }


def extract_records(db_path: Path) -> list[dict]:
    db_copy = copy_db(db_path)
    records = []

    con = sqlite3.connect(db_copy)
    try:
        rows = con.execute("select rowid, taskID, msg, time from task order by rowid").fetchall()
    finally:
        con.close()

    for rowid, task_id, msg, task_time in rows:
        try:
            payload = json.loads(msg)
        except json.JSONDecodeError:
            records.append(build_preserved_record(task_time, task_id, "", msg, "原始JSON解析失败", db_path, rowid))
            continue

        task = payload.get("task", {})
        documents = task.get("documents", [])
        if not documents:
            records.append(build_preserved_record(task_time, task_id, "", compact_json(payload), "未找到打印文档", db_path, rowid))
            continue

        for document in documents:
            document_id = document.get("documentID", "")
            text_chunks = []
            data_chunks = []
            for content in document.get("contents", []):
                text_chunks.extend(iter_text_nodes(content.get("printXML", "")))
                data = content.get("data")
                if isinstance(data, dict):
                    data_chunks.extend(data_text_lines(data))

            raw_chunks = []
            for chunk in text_chunks + data_chunks:
                append_unique(raw_chunks, chunk)
            raw_print_text = "\n".join(raw_chunks).strip()
            extract_status = "已提取文字" if raw_print_text else "未提取文字"
            if not raw_print_text:
                raw_print_text = raw_document_text(task_id, document_id, document)

            print_text = normalize_print_text(raw_print_text)
            if not print_text:
                print_text = raw_print_text.strip() or "[无打印信息]"

            record = {
                "task_time": task_time,
                "task_id": task_id,
                "document_id": document_id,
                "print_text": print_text,
                "print_text_raw": raw_print_text or print_text,
                "extract_status": extract_status,
                **record_source_fields(db_path, rowid),
            }
            records.append(record)

    return records


def collect_records() -> list[dict]:
    records = []
    for db_path in db_paths():
        records.extend(extract_records(db_path))
    return records


def extract_and_export_once() -> dict:
    records = collect_records()
    result = export_records(records)
    result["components"] = component_status()
    return result
