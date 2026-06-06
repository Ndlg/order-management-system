# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from utils.order_secure_common import get_data_dir


COLLECTION_MODE_FILTERED = "filtered"
COLLECTION_MODE_FULL = "full"
ALLOWED_COLLECTION_MODES = (COLLECTION_MODE_FILTERED, COLLECTION_MODE_FULL)
DEFAULT_COLLECTOR_ID = "default"
CONFIG_FILENAME = "collector_settings.json"
CONFIG_LOG_FILENAME = "collector_settings.log"


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def parse_config_time(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def is_newer_config_time(left: object, right: object) -> bool:
    left_dt = parse_config_time(left)
    right_dt = parse_config_time(right)
    if left_dt is None:
        return False
    if right_dt is None:
        return True
    return left_dt > right_dt


def validate_collection_mode(value: object) -> str:
    mode = str(value or "").strip().lower()
    if mode not in ALLOWED_COLLECTION_MODES:
        raise ValueError(f"invalid collection_mode: {value!r}")
    return mode


def collector_data_dir() -> Path:
    path = Path(get_data_dir()) / "waybill-monitor"
    path.mkdir(parents=True, exist_ok=True)
    return path


def collector_config_path() -> Path:
    return collector_data_dir() / CONFIG_FILENAME


def collector_config_log_path() -> Path:
    return collector_data_dir() / CONFIG_LOG_FILENAME


def default_collector_config(updated_by: str = "system") -> dict[str, Any]:
    return {
        "collection_mode": COLLECTION_MODE_FILTERED,
        "allowed_modes": list(ALLOWED_COLLECTION_MODES),
        "collector_id": DEFAULT_COLLECTOR_ID,
        "updated_at": utc_now_text(),
        "updated_by": updated_by or "system",
    }


def normalize_collector_config(raw: object | None = None) -> dict[str, Any]:
    config = default_collector_config()
    if isinstance(raw, dict):
        config.update(raw)
    try:
        config["collection_mode"] = validate_collection_mode(config.get("collection_mode"))
    except ValueError:
        config["collection_mode"] = COLLECTION_MODE_FILTERED
    config["allowed_modes"] = list(ALLOWED_COLLECTION_MODES)
    config["collector_id"] = str(config.get("collector_id") or DEFAULT_COLLECTOR_ID).strip() or DEFAULT_COLLECTOR_ID
    config["updated_by"] = str(config.get("updated_by") or "system").strip() or "system"
    if not parse_config_time(config.get("updated_at")):
        config["updated_at"] = utc_now_text()
    return config


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def append_config_log(old_mode: str, new_mode: str, updated_by: str, collector_id: str) -> None:
    path = collector_config_log_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    line = (
        f"{utc_now_text()} collection_mode {old_mode}->{new_mode} "
        f"updated_by={updated_by or 'system'} collector_id={collector_id or DEFAULT_COLLECTOR_ID}\n"
    )
    with path.open("a", encoding="utf-8", newline="\n") as file:
        file.write(line)


def load_collector_config(auto_create: bool = True) -> dict[str, Any]:
    path = collector_config_path()
    if not path.exists():
        config = default_collector_config()
        if auto_create:
            write_json_atomic(path, config)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    config = normalize_collector_config(raw)
    if auto_create:
        write_json_atomic(path, config)
    return config


def save_collector_config(
    collection_mode: object,
    updated_by: str = "system",
    collector_id: str = DEFAULT_COLLECTOR_ID,
    requested_updated_at: object | None = None,
) -> dict[str, Any]:
    mode = validate_collection_mode(collection_mode)
    current = load_collector_config(auto_create=False)
    old_mode = str(current.get("collection_mode") or COLLECTION_MODE_FILTERED)
    config = normalize_collector_config(current)
    config["collection_mode"] = mode
    config["collector_id"] = str(collector_id or config.get("collector_id") or DEFAULT_COLLECTOR_ID).strip() or DEFAULT_COLLECTOR_ID
    config["updated_by"] = str(updated_by or "system").strip() or "system"
    config["updated_at"] = str(requested_updated_at or "").strip() or utc_now_text()
    write_json_atomic(collector_config_path(), config)
    if old_mode != mode:
        append_config_log(old_mode, mode, config["updated_by"], config["collector_id"])
    return config


def maybe_accept_collector_config(payload: dict[str, Any]) -> dict[str, Any]:
    incoming_mode = payload.get("collection_mode")
    if incoming_mode in (None, ""):
        return load_collector_config()
    mode = validate_collection_mode(incoming_mode)
    current = load_collector_config()
    incoming_updated_at = payload.get("collector_config_updated_at") or payload.get("updated_at")
    if mode != current.get("collection_mode") and is_newer_config_time(incoming_updated_at, current.get("updated_at")):
        return save_collector_config(
            mode,
            updated_by="collector",
            collector_id=str(payload.get("client_id") or DEFAULT_COLLECTOR_ID),
            requested_updated_at=incoming_updated_at,
        )
    return current


def public_collector_config(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = normalize_collector_config(config or load_collector_config())
    return {
        "collection_mode": config["collection_mode"],
        "allowed_modes": list(ALLOWED_COLLECTION_MODES),
        "collector_id": config["collector_id"],
        "updated_at": config["updated_at"],
        "updated_by": config["updated_by"],
    }
