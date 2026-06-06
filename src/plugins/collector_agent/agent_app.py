# -*- coding: utf-8 -*-
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    src_root = Path(__file__).resolve().parents[2]
    if str(src_root) not in sys.path:
        sys.path.insert(0, str(src_root))
    __package__ = "plugins.collector_agent"

from . import agent_db_reader
from .agent_auth import register_with_server
from .agent_config import load_config, runtime_paths_public, save_config
from .agent_models import AGENT_VERSION, OFFICIAL_NAME, PROTOCOL_VERSION
from .agent_service import CollectorAgentService


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=OFFICIAL_NAME)
    parser.add_argument("--server-url", help="Web server URL.")
    parser.add_argument("--register", action="store_true", help="Register this business machine with the Web server.")
    parser.add_argument("--machine-label", help="Business machine display name.")
    parser.add_argument("--print-config", action="store_true", help="Print runtime paths and config.")
    parser.add_argument("--check-components", action="store_true", help="Check local print component database status.")
    parser.add_argument("--once", action="store_true", help="Run one poll/upload cycle.")
    parser.add_argument("--run", action="store_true", help="Run background polling service.")
    parser.add_argument("--minimized", action="store_true", help="Start GUI minimized to tray.")
    parser.add_argument("--self-test", action="store_true", help="Run a startup self-test.")
    return parser.parse_args(argv)


def print_json(payload: object) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def self_test() -> int:
    paths = runtime_paths_public()
    config = load_config()
    status = agent_db_reader.component_status()
    ok = bool(paths.get("config_dir")) and config.get("agent_version") == AGENT_VERSION
    print_json({"ok": ok, "agent_version": AGENT_VERSION, "protocol_version": PROTOCOL_VERSION, "paths": paths, "components": status})
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    config = load_config()
    changed = False
    if args.server_url:
        config["server_url"] = args.server_url
        changed = True
    if args.machine_label:
        config["machine_label"] = args.machine_label
        changed = True
    if changed:
        config = save_config(config)

    if args.register:
        config = register_with_server(config["server_url"], args.machine_label or config.get("machine_label", ""))
        print_json({"ok": True, "client_id": config.get("client_id"), "machine_label": config.get("machine_label")})
        return 0
    if args.print_config:
        print_json({"paths": runtime_paths_public(), "config": load_config()})
        return 0
    if args.check_components:
        print_json({"ok": True, "components": agent_db_reader.component_status()})
        return 0
    if args.self_test:
        return self_test()
    service = CollectorAgentService(config)
    if args.once:
        print_json(service.sync_once())
        return 0
    if args.run:
        service.run_forever()
        return 0

    from .agent_ui import run_app

    run_app(start_minimized=args.minimized)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
