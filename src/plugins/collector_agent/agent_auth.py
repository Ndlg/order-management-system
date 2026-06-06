# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any

from .agent_client import CollectorApiClient
from .agent_config import load_config, save_config


def bind_with_code(server_url: str, bind_code: str, machine_label: str = "", username: str = "") -> dict[str, Any]:
    config = load_config()
    config["server_url"] = server_url or config.get("server_url")
    if machine_label:
        config["machine_label"] = machine_label
    if username:
        config["username"] = username
    client = CollectorApiClient(config["server_url"])
    payload = {
        "bind_code": bind_code,
        "username": username,
        "client_id": config.get("client_id"),
        "machine_name": config.get("machine_name"),
        "machine_label": config.get("machine_label"),
        "hostname": config.get("hostname"),
        "platform": config.get("platform"),
        "agent_version": config.get("agent_version"),
        "protocol_version": config.get("protocol_version"),
    }
    response = client.bind(payload)
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "bind_failed")
    config["client_id"] = response.get("client_id") or config.get("client_id")
    config["agent_token"] = response.get("agent_token") or config.get("agent_token")
    config["machine_name"] = response.get("machine_name") or config.get("machine_name")
    config["machine_label"] = response.get("machine_label") or config.get("machine_label")
    return save_config(config)
