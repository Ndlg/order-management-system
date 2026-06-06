# -*- coding: utf-8 -*-
from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urljoin


class CollectorApiError(RuntimeError):
    pass


class CollectorApiClient:
    def __init__(self, server_url: str, agent_token: str = "", timeout: int = 10):
        self.server_url = str(server_url or "").rstrip("/") + "/"
        self.agent_token = str(agent_token or "")
        self.timeout = timeout

    def request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        body = None
        headers = {"Accept": "application/json"}
        if payload is not None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json; charset=utf-8"
        if self.agent_token:
            headers["Authorization"] = f"Bearer {self.agent_token}"
        request = urllib.request.Request(urljoin(self.server_url, path.lstrip("/")), data=body, headers=headers, method=method)
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                text = response.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="replace")
            raise CollectorApiError(f"http_{exc.code}: {detail}") from exc
        except urllib.error.URLError as exc:
            raise CollectorApiError(str(exc.reason)) from exc
        try:
            data = json.loads(text or "{}")
        except json.JSONDecodeError as exc:
            raise CollectorApiError(f"invalid_json_response: {text[:200]}") from exc
        if isinstance(data, dict):
            return data
        raise CollectorApiError("response_must_be_object")

    def bind(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/collector/bind", payload)

    def poll(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/collector/poll", payload)

    def upload(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self.request("POST", "/api/collector/upload", payload)

    def version_info(self) -> dict[str, Any]:
        return self.request("GET", "/api/collector/version-info")
