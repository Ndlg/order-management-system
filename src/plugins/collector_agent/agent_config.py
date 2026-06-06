# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import os
import platform
import socket
import uuid
from pathlib import Path
from typing import Any

from .agent_models import AGENT_VERSION, DEFAULT_SERVER_URL, PROTOCOL_VERSION


CONFIG_FILENAME = "agent_config.json"


def data_root() -> Path:
    override = os.environ.get("ORDER_COLLECTOR_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "OrderSystemCollector"
    return Path.home() / ".ordersystemcollector"


def program_dir() -> Path:
    if os.name == "nt":
        return Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "OrderSystemCollector"
    return Path(__file__).resolve().parents[3]


def config_dir() -> Path:
    return data_root() / "config"


def logs_dir() -> Path:
    return data_root() / "logs"


def cache_dir() -> Path:
    return data_root() / "cache"


def pending_uploads_dir() -> Path:
    return data_root() / "pending_uploads"


def ensure_runtime_dirs() -> None:
    for path in (config_dir(), logs_dir(), cache_dir(), pending_uploads_dir()):
        path.mkdir(parents=True, exist_ok=True)


def config_path() -> Path:
    ensure_runtime_dirs()
    return config_dir() / CONFIG_FILENAME


def runtime_paths_public() -> dict[str, str]:
    ensure_runtime_dirs()
    return {
        "program_dir": str(program_dir()),
        "data_dir": str(data_root()),
        "config_dir": str(config_dir()),
        "logs_dir": str(logs_dir()),
        "cache_dir": str(cache_dir()),
        "pending_uploads_dir": str(pending_uploads_dir()),
        "config_path": str(config_path()),
    }


def default_config() -> dict[str, Any]:
    machine_name = socket.gethostname() or "business-machine"
    return {
        "client_id": uuid.uuid4().hex,
        "server_url": DEFAULT_SERVER_URL,
        "agent_token": "",
        "machine_name": machine_name,
        "machine_label": machine_name,
        "hostname": machine_name,
        "username": os.environ.get("USERNAME") or os.environ.get("USER") or "",
        "platform": platform.platform(),
        "agent_version": AGENT_VERSION,
        "protocol_version": PROTOCOL_VERSION,
        "poll_interval_seconds": 2,
    }


def normalize_config(raw: object | None = None) -> dict[str, Any]:
    config = default_config()
    if isinstance(raw, dict):
        config.update(raw)
    for key in ("client_id", "server_url", "machine_name", "machine_label", "hostname", "username", "platform"):
        config[key] = str(config.get(key) or default_config().get(key) or "").strip()
    config["agent_token"] = str(config.get("agent_token") or "")
    config["agent_version"] = AGENT_VERSION
    config["protocol_version"] = PROTOCOL_VERSION
    try:
        config["poll_interval_seconds"] = max(1, int(config.get("poll_interval_seconds") or 2))
    except (TypeError, ValueError):
        config["poll_interval_seconds"] = 2
    return config


def load_config(auto_create: bool = True) -> dict[str, Any]:
    path = config_path()
    if not path.exists():
        config = normalize_config()
        if auto_create:
            save_config(config)
        return config
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        raw = {}
    config = normalize_config(raw)
    if auto_create:
        save_config(config)
    return config


def save_config(config: dict[str, Any]) -> dict[str, Any]:
    normalized = normalize_config(config)
    path = config_path()
    tmp = path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(normalized, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)
    return normalized


def update_config(**changes: Any) -> dict[str, Any]:
    config = load_config()
    config.update(changes)
    return save_config(config)
