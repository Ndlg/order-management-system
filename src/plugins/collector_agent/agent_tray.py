# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from .agent_config import data_root, logs_dir


def open_data_dir() -> None:
    path = data_root()
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def open_logs_dir() -> None:
    path = logs_dir()
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        os.startfile(str(path))  # type: ignore[attr-defined]
    else:
        subprocess.Popen(["xdg-open", str(path)])


def startup_shortcut_path() -> Path:
    startup = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
    return startup / "OrderCollectorAgent.cmd"


def enable_startup(executable: str | None = None) -> Path:
    if os.name != "nt":
        raise RuntimeError("startup_supported_on_windows_only")
    exe = executable or sys.executable
    path = startup_shortcut_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f'@echo off\nstart "" "{exe}" --run\n', encoding="utf-8")
    return path


def disable_startup() -> None:
    path = startup_shortcut_path()
    if path.exists():
        path.unlink()


class TrayController:
    """Placeholder tray adapter.

    The production EXE can run as a background service from --run. A richer tray
    library can be added later without changing the service contract.
    """

    def __init__(self, service):
        self.service = service

    def run(self) -> None:
        self.service.run_forever()
