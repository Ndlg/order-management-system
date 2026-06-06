# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path
from typing import Any

from .agent_config import cache_dir, pending_uploads_dir
from .agent_models import upload_dedupe_key, utc_now_text


CURSORS_FILENAME = "cursors.json"
BASELINES_FILENAME = "baselines.json"


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
    os.replace(tmp, path)


def cursors_path() -> Path:
    return cache_dir() / CURSORS_FILENAME


def baselines_path() -> Path:
    return cache_dir() / BASELINES_FILENAME


def load_cursors() -> dict[str, int]:
    raw = read_json(cursors_path(), {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, int] = {}
    for key, value in raw.items():
        try:
            result[str(key)] = int(value)
        except (TypeError, ValueError):
            result[str(key)] = 0
    return result


def save_cursors(cursors: dict[str, int]) -> None:
    write_json_atomic(cursors_path(), cursors)


def update_cursors_from_records(records: list[dict[str, Any]]) -> None:
    cursors = load_cursors()
    for record in records:
        db_id = str(record.get("component_db_id") or "")
        if not db_id:
            continue
        try:
            rowid = int(record.get("component_rowid") or 0)
        except (TypeError, ValueError):
            rowid = 0
        cursors[db_id] = max(int(cursors.get(db_id) or 0), rowid)
    save_cursors(cursors)


def load_baselines() -> dict[str, dict[str, int]]:
    raw = read_json(baselines_path(), {})
    if not isinstance(raw, dict):
        return {}
    result: dict[str, dict[str, int]] = {}
    for batch_id, values in raw.items():
        if not isinstance(values, dict):
            continue
        result[str(batch_id)] = {str(key): int(value or 0) for key, value in values.items()}
    return result


def save_batch_baseline(batch_id: str, baseline: dict[str, int]) -> None:
    baselines = load_baselines()
    baselines[str(batch_id)] = {str(key): int(value or 0) for key, value in baseline.items()}
    write_json_atomic(baselines_path(), baselines)


def load_batch_baseline(batch_id: str) -> dict[str, int]:
    return load_baselines().get(str(batch_id), {})


def clear_batch_baseline(batch_id: str) -> None:
    baselines = load_baselines()
    baselines.pop(str(batch_id), None)
    write_json_atomic(baselines_path(), baselines)


def pending_file_path(batch_id: str) -> Path:
    safe = "".join(ch if ch.isalnum() or ch in "-_." else "_" for ch in str(batch_id or "batch")).strip("_") or "batch"
    return pending_uploads_dir() / f"{safe}_{uuid.uuid4().hex}.json"


def write_pending_upload(payload: dict[str, Any]) -> Path:
    payload = dict(payload)
    payload.setdefault("pending_id", uuid.uuid4().hex)
    payload.setdefault("created_at", utc_now_text())
    path = pending_file_path(str(payload.get("batch_id") or "batch"))
    write_json_atomic(path, payload)
    return path


def iter_pending_uploads() -> list[tuple[Path, dict[str, Any]]]:
    pending_uploads_dir().mkdir(parents=True, exist_ok=True)
    rows: list[tuple[Path, dict[str, Any]]] = []
    for path in sorted(pending_uploads_dir().glob("*.json"), key=lambda item: item.stat().st_mtime):
        data = read_json(path, {})
        if isinstance(data, dict):
            rows.append((path, data))
    return rows


def delete_pending(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def dedupe_records_for_payload(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for row in records:
        key = upload_dedupe_key(row)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result
