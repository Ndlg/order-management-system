# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

from order_secure_common import get_data_dir
from waybill_files import export_records


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


def extract_records(db_path: Path) -> list[dict]:
    db_copy = copy_db(db_path)
    records = []

    con = sqlite3.connect(db_copy)
    try:
        rows = con.execute("select taskID, msg, time from task order by rowid").fetchall()
    finally:
        con.close()

    for task_id, msg, task_time in rows:
        try:
            payload = json.loads(msg)
        except json.JSONDecodeError:
            continue

        task = payload.get("task", {})
        for document in task.get("documents", []):
            document_id = document.get("documentID", "")
            text_chunks = []
            data_chunks = []
            for content in document.get("contents", []):
                text_chunks.extend(iter_text_nodes(content.get("printXML", "")))
                data = content.get("data")
                if isinstance(data, dict):
                    product_text = choose_product_text(data)
                    if product_text:
                        data_chunks.append(product_text)

            raw_print_text = "\n".join(text_chunks or data_chunks).strip()
            print_text = normalize_print_text(raw_print_text)
            if not print_text:
                continue

            record = {
                "task_time": task_time,
                "task_id": task_id,
                "document_id": document_id,
                "print_text": print_text,
                "print_text_raw": raw_print_text or print_text,
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
