# -*- coding: utf-8 -*-
from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Callable

from .agent_config import data_root, logs_dir


def icon_path(name: str) -> Path:
    candidates: list[Path] = []
    bundle_root = getattr(sys, "_MEIPASS", None)
    if bundle_root:
        candidates.append(Path(bundle_root) / "plugins" / "collector_agent" / "assets" / name)
    candidates.append(Path(__file__).resolve().parent / "assets" / name)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


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
    path.write_text(f'@echo off\nstart "" "{exe}" --minimized\n', encoding="utf-8")
    return path


def disable_startup() -> None:
    path = startup_shortcut_path()
    if path.exists():
        path.unlink()


def startup_enabled() -> bool:
    return startup_shortcut_path().exists()


class AgentTray:
    def __init__(
        self,
        status_getter: Callable[[], str],
        show_window: Callable[[], None],
        reconnect: Callable[[], None],
        quit_app: Callable[[], None],
    ):
        self.status_getter = status_getter
        self.show_window = show_window
        self.reconnect = reconnect
        self.quit_app = quit_app
        self.icon = None
        self.thread: threading.Thread | None = None

    def available(self) -> bool:
        try:
            import pystray  # noqa: F401
            from PIL import Image  # noqa: F401
        except Exception:
            return False
        return True

    def start(self) -> None:
        if not self.available() or self.icon is not None:
            return
        import pystray

        self.icon = pystray.Icon(
            "OrderCollectorAgent",
            self._image(),
            "订单整理系统 - 业务机采集助手",
            self._menu(),
        )
        self.thread = threading.Thread(target=self.icon.run, name="collector-agent-tray", daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.icon is not None:
            self.icon.stop()
            self.icon = None

    def notify(self, title: str, message: str) -> None:
        if self.icon is not None:
            try:
                self.icon.notify(message, title)
            except Exception:
                pass

    def _menu(self):
        import pystray

        return pystray.Menu(
            pystray.MenuItem("打开主界面", lambda: self.show_window()),
            pystray.MenuItem(lambda _: f"当前状态：{self.status_getter()}", None, enabled=False),
            pystray.MenuItem("立即重连", lambda: self.reconnect()),
            pystray.MenuItem("查看日志", lambda: open_logs_dir()),
            pystray.MenuItem(
                "开机启动",
                lambda: self._toggle_startup(),
                checked=lambda _: startup_enabled(),
            ),
            pystray.MenuItem("退出", lambda: self.quit_app()),
        )

    def _toggle_startup(self) -> None:
        if startup_enabled():
            disable_startup()
        else:
            enable_startup()

    def _image(self):
        from PIL import Image, ImageDraw

        source = icon_path("collector_agent_icon.png")
        if source.exists():
            try:
                return Image.open(source).convert("RGBA")
            except Exception:
                pass
        image = Image.new("RGBA", (64, 64), (37, 99, 168, 255))
        draw = ImageDraw.Draw(image)
        draw.rounded_rectangle((6, 6, 58, 58), radius=12, fill=(22, 128, 96, 255))
        draw.rectangle((18, 18, 46, 25), fill=(255, 255, 255, 255))
        draw.rectangle((18, 30, 46, 37), fill=(255, 255, 255, 255))
        draw.rectangle((18, 42, 38, 49), fill=(255, 255, 255, 255))
        return image
