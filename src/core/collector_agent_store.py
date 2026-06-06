# -*- coding: utf-8 -*-
from __future__ import annotations

import hashlib
import json
import uuid
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.order_secure_common import get_data_dir


COLLECTOR_PROTOCOL_VERSION = "collector.v1"
LATEST_AGENT_VERSION = "7.9.3"
MIN_SUPPORTED_AGENT_VERSION = "7.9.3"
COLLECTOR_ONLINE_SECONDS = 30
RAW_RECORDS_FILENAME = "collector_raw_records.jsonl"
UPLOAD_LOGS_FILENAME = "collector_upload_logs.jsonl"
NO_PRINT_TEXT_PLACEHOLDER = "[未提取到打印文字，已保留原始打印任务]"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    for candidate in (text, text[:19]):
        try:
            dt = datetime.fromisoformat(candidate)
            if dt.tzinfo is None:
                return dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            continue
    return None


def is_recent(value: object, max_age_seconds: int = COLLECTOR_ONLINE_SECONDS) -> bool:
    dt = parse_time(value)
    if not dt:
        return False
    return (datetime.now(timezone.utc) - dt).total_seconds() <= max_age_seconds


def parse_version(value: object) -> tuple[int, int, int]:
    parts = str(value or "").strip().lstrip("vV").split(".")
    numbers: list[int] = []
    for part in parts[:3]:
        try:
            numbers.append(int(part))
        except ValueError:
            numbers.append(0)
    while len(numbers) < 3:
        numbers.append(0)
    return tuple(numbers[:3])


def agent_needs_upgrade(agent_version: object, protocol_version: object) -> bool:
    if str(protocol_version or "").strip() != COLLECTOR_PROTOCOL_VERSION:
        return True
    return parse_version(agent_version) < parse_version(MIN_SUPPORTED_AGENT_VERSION)


def collector_data_dir() -> Path:
    path = Path(get_data_dir()) / "waybill-monitor" / "collector_agent"
    path.mkdir(parents=True, exist_ok=True)
    return path


def agents_path() -> Path:
    return collector_data_dir() / "collector_agents.json"


def raw_records_path() -> Path:
    return collector_data_dir() / RAW_RECORDS_FILENAME


def upload_logs_path() -> Path:
    return collector_data_dir() / UPLOAD_LOGS_FILENAME


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return default


def write_json_atomic(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def append_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8", newline="\n") as file:
        for row in rows:
            file.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n")


def iter_jsonl(path: Path, limit: int | None = None) -> list[dict[str, Any]]:
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


def token_hash(token: str) -> str:
    return hashlib.sha256(str(token or "").encode("utf-8")).hexdigest()


def compact_json(value: object) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str, separators=(",", ":"))
    except TypeError:
        return str(value)


def load_agents() -> dict[str, dict[str, Any]]:
    value = read_json(agents_path(), {})
    return value if isinstance(value, dict) else {}


def save_agents(agents: dict[str, dict[str, Any]]) -> None:
    write_json_atomic(agents_path(), agents)


def version_info(download_url: str = "") -> dict[str, Any]:
    return {
        "server_version": LATEST_AGENT_VERSION,
        "protocol_version": COLLECTOR_PROTOCOL_VERSION,
        "min_supported_agent_version": MIN_SUPPORTED_AGENT_VERSION,
        "latest_agent_version": LATEST_AGENT_VERSION,
        "upgrade_required": False,
        "upgrade_message": "",
        "download_url": download_url,
    }


def register_agent(payload: dict[str, Any]) -> tuple[dict[str, Any] | None, str]:
    client_id = str(payload.get("client_id") or uuid.uuid4().hex).strip()
    if not client_id:
        return None, "client_id_required"
    token = uuid.uuid4().hex + uuid.uuid4().hex
    now = utc_now_text()
    agents = load_agents()
    current = agents.get(client_id, {})
    machine_name = str(payload.get("machine_name") or current.get("machine_name") or client_id).strip()
    machine_label = str(payload.get("machine_label") or current.get("machine_label") or machine_name).strip()
    agents[client_id] = {
        **current,
        "client_id": client_id,
        "machine_name": machine_name,
        "machine_label": machine_label,
        "hostname": str(payload.get("hostname") or current.get("hostname") or ""),
        "username": str(payload.get("username") or payload.get("windows_user") or current.get("username") or ""),
        "platform": str(payload.get("platform") or current.get("platform") or ""),
        "agent_version": str(payload.get("agent_version") or current.get("agent_version") or ""),
        "protocol_version": str(payload.get("protocol_version") or current.get("protocol_version") or ""),
        "token_hash": token_hash(token),
        "last_seen": now,
        "component_status": payload.get("component_status") if isinstance(payload.get("component_status"), list) else [],
        "created_at": current.get("created_at") or now,
        "updated_at": now,
    }
    save_agents(agents)
    return {
        "client_id": client_id,
        "agent_token": token,
        "machine_name": machine_name,
        "machine_label": machine_label,
    }, ""


def extract_token(payload: dict[str, Any], authorization: str = "") -> str:
    text = str(authorization or "").strip()
    if text.lower().startswith("bearer "):
        return text[7:].strip()
    return str(payload.get("agent_token") or payload.get("token") or "").strip()


def authenticate_agent(payload: dict[str, Any], authorization: str = "") -> tuple[dict[str, Any] | None, str]:
    client_id = str(payload.get("client_id") or "").strip()
    token = extract_token(payload, authorization)
    if not client_id or not token:
        return None, "agent_token_required"
    agents = load_agents()
    agent = agents.get(client_id)
    if not agent or agent.get("token_hash") != token_hash(token):
        return None, "agent_token_invalid"
    return agent, ""


def upsert_agent_from_poll(payload: dict[str, Any], existing: dict[str, Any]) -> dict[str, Any]:
    agents = load_agents()
    client_id = str(payload.get("client_id") or existing.get("client_id") or "").strip()
    current = dict(agents.get(client_id, existing))
    now = utc_now_text()
    component_status = payload.get("component_status")
    if not isinstance(component_status, list):
        component_status = payload.get("components") if isinstance(payload.get("components"), list) else []
    current.update(
        {
            "client_id": client_id,
            "machine_name": str(payload.get("machine_name") or current.get("machine_name") or client_id),
            "machine_label": str(payload.get("machine_label") or current.get("machine_label") or client_id),
            "hostname": str(payload.get("hostname") or current.get("hostname") or ""),
            "username": str(payload.get("username") or current.get("username") or ""),
            "platform": str(payload.get("platform") or current.get("platform") or ""),
            "agent_version": str(payload.get("agent_version") or current.get("agent_version") or ""),
            "protocol_version": str(payload.get("protocol_version") or current.get("protocol_version") or ""),
            "component_status": component_status,
            "active_batch_id": str(payload.get("active_batch_id") or ""),
            "last_seen": str(payload.get("last_seen") or now),
            "updated_at": now,
        }
    )
    agents[client_id] = current
    save_agents(agents)
    return current


def public_agent(row: dict[str, Any]) -> dict[str, Any]:
    component_status = row.get("component_status") if isinstance(row.get("component_status"), list) else []
    upgrade = agent_needs_upgrade(row.get("agent_version"), row.get("protocol_version"))
    return {
        "client_id": row.get("client_id", ""),
        "machine_name": row.get("machine_name", ""),
        "machine_label": row.get("machine_label", ""),
        "hostname": row.get("hostname", ""),
        "username": row.get("username", ""),
        "platform": row.get("platform", ""),
        "agent_version": row.get("agent_version", ""),
        "protocol_version": row.get("protocol_version", ""),
        "component_status": component_status,
        "components": component_status,
        "component_count": len(component_status),
        "available_components": len([item for item in component_status if isinstance(item, dict) and item.get("exists")]),
        "last_seen": row.get("last_seen", ""),
        "online": is_recent(row.get("last_seen")),
        "created_at": row.get("created_at", ""),
        "updated_at": row.get("updated_at", ""),
        "last_upload_at": row.get("last_upload_at", ""),
        "last_upload_count": int(row.get("last_upload_count") or 0),
        "upgrade_required": upgrade,
        "upgrade_message": "打印组件信息采集需要升级" if upgrade else "",
        "download_url": row.get("download_url", ""),
    }


def list_agents_public() -> list[dict[str, Any]]:
    rows = [public_agent(row) for row in load_agents().values()]
    return sorted(rows, key=lambda item: (not item.get("online"), str(item.get("machine_label") or item.get("client_id"))))


def upload_dedupe_key(row: dict[str, Any]) -> tuple[str, str, str, str, str, str]:
    return (
        str(row.get("client_id") or row.get("source_client_id") or ""),
        str(row.get("component_db_id") or ""),
        str(row.get("component_rowid") or ""),
        str(row.get("task_id") or ""),
        str(row.get("document_id") or ""),
        str(row.get("source_record_index") or ""),
    )


def existing_upload_keys() -> set[tuple[str, str, str, str, str, str]]:
    keys: set[tuple[str, str, str, str, str, str]] = set()
    for row in iter_jsonl(raw_records_path()):
        key = upload_dedupe_key(row)
        if any(key[1:]):
            keys.add(key)
    return keys


def build_raw_record(row: dict[str, Any], payload: dict[str, Any], agent: dict[str, Any]) -> dict[str, Any]:
    now = utc_now_text()
    client_id = str(payload.get("client_id") or agent.get("client_id") or row.get("client_id") or "")
    machine_name = str(payload.get("machine_name") or agent.get("machine_name") or row.get("machine_name") or "")
    machine_label = str(payload.get("machine_label") or agent.get("machine_label") or row.get("machine_label") or machine_name)
    print_text_raw = str(row.get("print_text_raw") or row.get("print_text") or "").strip() or NO_PRINT_TEXT_PLACEHOLDER
    raw_msg_json = compact_json(row.get("raw_msg_json"))
    raw_document_json = compact_json(row.get("raw_document_json"))
    raw_hash_source = "|".join([raw_msg_json, raw_document_json, print_text_raw])
    record_id = uuid.uuid4().hex
    return {
        "id": record_id,
        "record_id": record_id,
        "client_id": client_id,
        "source_client_id": client_id,
        "machine_name": machine_name,
        "machine_label": machine_label,
        "agent_version": str(payload.get("agent_version") or row.get("agent_version") or agent.get("agent_version") or ""),
        "protocol_version": str(payload.get("protocol_version") or row.get("protocol_version") or agent.get("protocol_version") or ""),
        "batch_id": str(payload.get("batch_id") or row.get("batch_id") or ""),
        "component_name": str(row.get("component_name") or ""),
        "component_db_id": str(row.get("component_db_id") or ""),
        "component_db_path": str(row.get("component_db_path") or ""),
        "component_rowid": row.get("component_rowid") if row.get("component_rowid") is not None else "",
        "task_id": str(row.get("task_id") or ""),
        "document_id": str(row.get("document_id") or ""),
        "task_time": str(row.get("task_time") or ""),
        "source_record_index": str(row.get("source_record_index") or ""),
        "raw_msg_json": raw_msg_json,
        "raw_document_json": raw_document_json,
        "print_text_raw": print_text_raw,
        "print_text": print_text_raw,
        "extract_status": str(row.get("extract_status") or "raw_preserved"),
        "raw_hash": hashlib.sha256(raw_hash_source.encode("utf-8", errors="ignore")).hexdigest(),
        "created_at": str(row.get("created_at") or now),
        "uploaded_at": now,
    }


def append_raw_records(records: list[dict[str, Any]], payload: dict[str, Any], agent: dict[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(records, list):
        raise ValueError("records_must_be_list")
    keys = existing_upload_keys()
    accepted: list[dict[str, Any]] = []
    seen_in_payload: set[tuple[str, str, str, str, str, str]] = set()
    for source in records:
        if not isinstance(source, dict):
            continue
        row = build_raw_record(source, payload, agent)
        key = upload_dedupe_key(row)
        if any(key[1:]) and (key in keys or key in seen_in_payload):
            continue
        accepted.append(row)
        seen_in_payload.add(key)

    append_jsonl(raw_records_path(), accepted)
    append_jsonl(
        upload_logs_path(),
        [
            {
                "id": uuid.uuid4().hex,
                "client_id": payload.get("client_id", ""),
                "batch_id": payload.get("batch_id", ""),
                "received": len(records),
                "accepted": len(accepted),
                "created_at": utc_now_text(),
            }
        ],
    )

    agents = load_agents()
    client_id = str(payload.get("client_id") or agent.get("client_id") or "")
    if client_id in agents:
        agents[client_id]["last_upload_at"] = utc_now_text()
        agents[client_id]["last_upload_count"] = len(accepted)
        agents[client_id]["updated_at"] = utc_now_text()
        save_agents(agents)
    return accepted


def public_raw_record(row: dict[str, Any], include_text: bool = False) -> dict[str, Any]:
    raw_text = str(row.get("print_text_raw") or "")
    payload = {
        "id": row.get("id", ""),
        "record_id": row.get("record_id") or row.get("id", ""),
        "batch_id": row.get("batch_id", ""),
        "client_id": row.get("client_id", ""),
        "machine_name": row.get("machine_name", ""),
        "machine_label": row.get("machine_label", ""),
        "component_name": row.get("component_name", ""),
        "component_rowid": row.get("component_rowid", ""),
        "component_db_id": row.get("component_db_id", ""),
        "task_id": row.get("task_id", ""),
        "document_id": row.get("document_id", ""),
        "task_time": row.get("task_time", ""),
        "source_record_index": row.get("source_record_index", ""),
        "extract_status": row.get("extract_status", ""),
        "raw_hash": row.get("raw_hash", ""),
        "print_text_preview": raw_text[:180],
        "raw_preview": raw_text[:180],
        "raw_length": len(raw_text),
        "agent_version": row.get("agent_version", ""),
        "protocol_version": row.get("protocol_version", ""),
        "created_at": row.get("created_at", ""),
        "uploaded_at": row.get("uploaded_at", ""),
    }
    if include_text:
        payload["print_text_raw"] = raw_text
        payload["raw_msg_json"] = row.get("raw_msg_json", "")
        payload["raw_document_json"] = row.get("raw_document_json", "")
    return payload


def list_raw_records(limit: int = 50, include_text: bool = False) -> list[dict[str, Any]]:
    limit = max(1, min(int(limit or 50), 500))
    rows = iter_jsonl(raw_records_path(), limit=limit)
    return [public_raw_record(row, include_text=include_text) for row in reversed(rows)]


def get_raw_record(record_id: str) -> dict[str, Any] | None:
    target = str(record_id or "").strip()
    if not target:
        return None
    for row in reversed(iter_jsonl(raw_records_path())):
        if str(row.get("record_id") or row.get("id") or "") == target:
            return public_raw_record(row, include_text=True)
    return None
