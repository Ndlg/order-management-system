# -*- coding: utf-8 -*-
from __future__ import annotations

import time
from typing import Any

from . import agent_db_reader, agent_storage
from .agent_client import CollectorApiClient, CollectorApiError
from .agent_config import load_config, save_config
from .agent_logger import setup_logger
from .agent_models import AGENT_VERSION, PROTOCOL_VERSION, ensure_required_fields, utc_now_text


class CollectorAgentService:
    def __init__(self, config: dict[str, Any] | None = None):
        self.config = config or load_config()
        self.logger = setup_logger()

    def client(self) -> CollectorApiClient:
        return CollectorApiClient(self.config.get("server_url", ""), self.config.get("agent_token", ""))

    def status_payload(self, active_batch_id: str = "") -> dict[str, Any]:
        return {
            "client_id": self.config.get("client_id", ""),
            "machine_name": self.config.get("machine_name", ""),
            "machine_label": self.config.get("machine_label", ""),
            "hostname": self.config.get("hostname", ""),
            "username": self.config.get("username", ""),
            "platform": self.config.get("platform", ""),
            "agent_version": AGENT_VERSION,
            "protocol_version": PROTOCOL_VERSION,
            "component_status": agent_db_reader.component_status(),
            "active_batch_id": active_batch_id,
            "last_seen": utc_now_text(),
        }

    def enrich_records(self, records: list[dict[str, Any]], batch_id: str) -> list[dict[str, Any]]:
        enriched: list[dict[str, Any]] = []
        for row in records:
            item = dict(row)
            item.update(
                {
                    "client_id": self.config.get("client_id", ""),
                    "machine_name": self.config.get("machine_name", ""),
                    "machine_label": self.config.get("machine_label", ""),
                    "agent_version": AGENT_VERSION,
                    "protocol_version": PROTOCOL_VERSION,
                    "batch_id": batch_id,
                }
            )
            enriched.append(ensure_required_fields(item))
        return agent_storage.dedupe_records_for_payload(enriched)

    def upload_payload(self, payload: dict[str, Any]) -> bool:
        response = self.client().upload(payload)
        if not response.get("ok"):
            raise CollectorApiError(str(response.get("error") or "upload_rejected"))
        accepted = int(response.get("accepted") or 0)
        if accepted:
            agent_storage.update_cursors_from_records(payload.get("records", []))
        return True

    def flush_pending_uploads(self) -> int:
        flushed = 0
        for path, payload in agent_storage.iter_pending_uploads():
            try:
                self.upload_payload(payload)
            except Exception as exc:
                self.logger.warning("pending_upload_failed path=%s error=%s", path, exc)
                continue
            agent_storage.delete_pending(path)
            flushed += 1
            self.logger.info("pending_upload_flushed path=%s", path)
        return flushed

    def handle_start(self, batch_id: str) -> None:
        if not batch_id:
            return
        if agent_storage.load_batch_baseline(batch_id):
            return
        baseline = agent_db_reader.current_max_rowids()
        agent_storage.save_batch_baseline(batch_id, baseline)
        self.logger.info("batch_start batch_id=%s baseline=%s", batch_id, baseline)

    def handle_stop(self, batch_id: str) -> dict[str, Any]:
        baseline = agent_storage.load_batch_baseline(batch_id)
        if not baseline:
            baseline = agent_storage.load_cursors()
        stop_rowids = agent_db_reader.current_max_rowids()
        records = self.enrich_records(agent_db_reader.collect_records(baseline, stop_rowids, batch_id=batch_id), batch_id)
        payload = {
            **self.status_payload(active_batch_id=batch_id),
            "batch_id": batch_id,
            "records_found": len(records),
            "records": records,
        }
        try:
            self.upload_payload(payload)
            agent_storage.clear_batch_baseline(batch_id)
            self.logger.info("batch_stop_uploaded batch_id=%s records=%s", batch_id, len(records))
            return {"ok": True, "pending": False, "records": len(records)}
        except Exception as exc:
            pending_path = agent_storage.write_pending_upload(payload)
            self.logger.warning("batch_stop_pending batch_id=%s records=%s path=%s error=%s", batch_id, len(records), pending_path, exc)
            return {"ok": False, "pending": True, "records": len(records), "error": str(exc), "path": str(pending_path)}

    def sync_once(self) -> dict[str, Any]:
        self.config = load_config()
        flushed = self.flush_pending_uploads()
        response = self.client().poll(self.status_payload())
        if not response.get("ok"):
            raise CollectorApiError(str(response.get("error") or "poll_rejected"))
        command = str(response.get("command") or "idle")
        batch_id = str(response.get("batch_id") or "")
        if command == "start":
            self.handle_start(batch_id)
        elif command == "stop":
            stop_result = self.handle_stop(batch_id)
            response["stop_result"] = stop_result
        elif command == "upgrade":
            self.logger.warning("upgrade_requested message=%s", response.get("upgrade_message", ""))
        response["pending_flushed"] = flushed
        return response

    def run_forever(self) -> None:
        self.logger.info("service_run_forever server=%s client_id=%s", self.config.get("server_url"), self.config.get("client_id"))
        while True:
            try:
                response = self.sync_once()
                interval = int(response.get("poll_interval_seconds") or self.config.get("poll_interval_seconds") or 2)
                save_config({**self.config, "poll_interval_seconds": interval})
            except Exception as exc:
                self.logger.warning("sync_once_failed error=%s", exc)
                interval = int(self.config.get("poll_interval_seconds") or 2)
            time.sleep(max(1, interval))
