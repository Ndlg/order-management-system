# -*- coding: utf-8 -*-
from __future__ import annotations

from . import agent_db_reader
from .agent_client import CollectorApiClient
from .agent_config import load_config, save_config


def register_with_server(server_url: str = "", machine_label: str = "") -> dict:
    config = load_config()
    config["server_url"] = server_url or config.get("server_url")
    if machine_label:
        config["machine_label"] = machine_label
    client = CollectorApiClient(config["server_url"])
    payload = {
        "client_id": config.get("client_id"),
        "machine_name": config.get("machine_name"),
        "machine_label": config.get("machine_label"),
        "hostname": config.get("hostname"),
        "username": config.get("username"),
        "platform": config.get("platform"),
        "agent_version": config.get("agent_version"),
        "protocol_version": config.get("protocol_version"),
        "component_status": agent_db_reader.component_status(),
    }
    response = client.register(payload)
    if not response.get("ok"):
        raise RuntimeError(response.get("error") or "register_failed")
    config["client_id"] = response.get("client_id") or config.get("client_id")
    config["agent_token"] = response.get("agent_token") or config.get("agent_token")
    config["machine_name"] = response.get("machine_name") or config.get("machine_name")
    config["machine_label"] = response.get("machine_label") or config.get("machine_label")
    return save_config(config)
