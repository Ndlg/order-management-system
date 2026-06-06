# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import time
import tkinter as tk
from datetime import datetime
from tkinter import messagebox, ttk
from typing import Any, Callable

from . import agent_db_reader
from .agent_auth import register_with_server
from .agent_config import load_config, runtime_paths_public, save_config
from .agent_models import AGENT_VERSION, OFFICIAL_NAME
from .agent_service import CollectorAgentService
from .agent_tray import AgentTray, disable_startup, enable_startup, icon_path, open_logs_dir, startup_enabled


def now_text() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def state_from_response(response: dict[str, Any]) -> dict[str, Any]:
    command = str(response.get("command") or "idle")
    batch_id = str(response.get("batch_id") or "")
    state = {
        "server_status": "已连接",
        "current_status": "待命",
        "current_task": "等待任务",
        "last_upload_time": "",
        "last_upload_count": "",
        "detail": "后台待命，等待 Web 任务指令",
    }
    if command == "start":
        state.update({"current_status": "采集中", "current_task": batch_id or "当前批次", "detail": "正在记录本机打印基准"})
    elif command == "stop":
        stop_result = response.get("stop_result") if isinstance(response.get("stop_result"), dict) else {}
        count = int(stop_result.get("records") or 0)
        state.update(
            {
                "current_status": "上传中" if count else "待命",
                "current_task": batch_id or "当前批次",
                "last_upload_time": now_text() if count else "",
                "last_upload_count": str(count) if count else "",
                "detail": "已上传本批次打印原文" if not stop_result.get("pending") else "Web 暂不可达，已进入待重试队列",
            }
        )
    elif command == "upgrade":
        state.update({"current_status": "需要升级", "current_task": "等待升级", "detail": response.get("upgrade_message") or "打印组件信息采集版本需要升级"})
    return state


class AgentRuntimeController:
    def __init__(self, on_state: Callable[[dict[str, Any]], None]):
        self.on_state = on_state
        self.config = load_config()
        self.service = CollectorAgentService(self.config)
        self.enabled = True
        self.running = False
        self.thread: threading.Thread | None = None
        self.wake = threading.Event()
        self.last_state: dict[str, Any] = {}

    def start(self) -> None:
        self.enabled = True
        if not self.thread or not self.thread.is_alive():
            self.running = True
            self.thread = threading.Thread(target=self._loop, name="collector-agent-heartbeat", daemon=True)
            self.thread.start()
        self.reconnect_now()

    def stop_service(self) -> None:
        self.enabled = False
        self._publish({"server_status": "服务已停止", "current_status": "已停止", "current_task": "-", "detail": "后台心跳已暂停"}, force=True)
        self.wake.set()

    def shutdown(self) -> None:
        self.running = False
        self.wake.set()

    def reconnect_now(self) -> None:
        self.enabled = True
        self.wake.set()

    def reload_config(self) -> None:
        self.config = load_config()
        self.service = CollectorAgentService(self.config)
        self.reconnect_now()

    def _loop(self) -> None:
        while self.running:
            if not self.enabled:
                self.wake.wait(1)
                self.wake.clear()
                continue
            self.config = load_config()
            self.service.config = self.config
            if not self.config.get("agent_token"):
                try:
                    self._publish(
                        {
                            "server_status": "上线注册中",
                            "current_status": "重连中",
                            "current_task": "自动注册业务机",
                            "detail": "正在向 Web 服务注册本业务机",
                            "component_text": self.component_text(),
                        }
                    )
                    self.config = register_with_server(self.config.get("server_url", ""), self.config.get("machine_label", ""))
                    self.service = CollectorAgentService(self.config)
                except Exception as exc:
                    if not self.enabled:
                        continue
                    self._publish(
                        {
                            "server_status": "重连中",
                            "current_status": "重连中",
                            "current_task": "等待 Web 服务恢复",
                            "detail": f"上线注册失败，自动重试中：{exc}",
                            "component_text": self.component_text(),
                        }
                    )
                    self.wake.wait(2)
                    self.wake.clear()
                    continue
            try:
                response = self.service.sync_once()
                if not self.enabled:
                    continue
                state = state_from_response(response)
                state["component_text"] = self.component_text()
                state["pending_flushed"] = response.get("pending_flushed", 0)
                self._publish(state)
                interval = int(response.get("poll_interval_seconds") or self.config.get("poll_interval_seconds") or 2)
            except Exception as exc:
                if not self.enabled:
                    continue
                if "agent_token_invalid" in str(exc) or "agent_token_required" in str(exc):
                    config = load_config()
                    config["agent_token"] = ""
                    save_config(config)
                self._publish(
                    {
                        "server_status": "重连中",
                        "current_status": "重连中",
                        "current_task": "等待 Web 服务恢复",
                        "detail": f"自动重试中：{exc}",
                        "component_text": self.component_text(),
                    }
                )
                interval = int(self.config.get("poll_interval_seconds") or 2)
            self.wake.wait(max(1, interval))
            self.wake.clear()

    def component_text(self) -> str:
        status = agent_db_reader.component_status()
        total = len(status)
        available = len([item for item in status if item.get("exists")])
        return f"正常 {available}/{total}" if total else "未检测到打印组件"

    def _publish(self, state: dict[str, Any], force: bool = False) -> None:
        if not force and not self.enabled:
            return
        state = {**self.last_state, **state}
        state.setdefault("last_upload_time", self.last_state.get("last_upload_time", "-"))
        state.setdefault("last_upload_count", self.last_state.get("last_upload_count", "-"))
        self.last_state = state
        self.on_state(state)


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent: "AgentWindow"):
        super().__init__(parent)
        self.parent = parent
        self.title("打印组件信息采集设置")
        self.resizable(False, False)
        self.config_data = load_config()
        self.transient(parent)
        self.grab_set()
        self.build()

    def build(self) -> None:
        body = ttk.Frame(self, padding=16)
        body.grid(row=0, column=0, sticky="nsew")
        self.server_var = tk.StringVar(value=str(self.config_data.get("server_url") or ""))
        self.label_var = tk.StringVar(value=str(self.config_data.get("machine_label") or self.config_data.get("machine_name") or ""))
        self.startup_var = tk.BooleanVar(value=startup_enabled())
        rows = [
            ("服务器地址", self.server_var),
            ("业务机名称", self.label_var),
        ]
        for index, (label, var) in enumerate(rows):
            ttk.Label(body, text=label).grid(row=index, column=0, sticky="w", pady=6)
            entry = ttk.Entry(body, textvariable=var, width=44)
            entry.grid(row=index, column=1, sticky="ew", padx=(12, 0), pady=6)
        ttk.Checkbutton(body, text="开机自动启动并最小化到托盘", variable=self.startup_var).grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 2))
        actions = ttk.Frame(body)
        actions.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(actions, text="保存", command=self.save).pack(side="left", padx=4)
        ttk.Button(actions, text="取消", command=self.destroy).pack(side="left", padx=4)

    def save(self) -> None:
        try:
            config = load_config()
            server_url = self.server_var.get().strip()
            machine_label = self.label_var.get().strip()
            should_reregister = (
                server_url != str(config.get("server_url") or "")
                or machine_label != str(config.get("machine_label") or config.get("machine_name") or "")
            )
            config["server_url"] = server_url
            config["machine_label"] = machine_label or config.get("machine_label") or config.get("machine_name")
            config["machine_name"] = config["machine_label"]
            if should_reregister:
                config["agent_token"] = ""
            save_config(config)
            if self.startup_var.get():
                enable_startup()
            else:
                disable_startup()
            self.parent.after_config_changed()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("设置保存失败", str(exc), parent=self)


class DiagnosticsDialog(tk.Toplevel):
    def __init__(self, parent: "AgentWindow"):
        super().__init__(parent)
        self.title("诊断信息")
        self.geometry("680x420")
        self.transient(parent)
        self.build()

    def build(self) -> None:
        config = load_config()
        components = agent_db_reader.component_status()
        paths = runtime_paths_public()
        lines = [
            f"client_id: {config.get('client_id', '')}",
            f"machine_name: {config.get('machine_name', '')}",
            f"machine_label: {config.get('machine_label', '')}",
            f"protocol_version: {config.get('protocol_version', '')}",
            f"server_url: {config.get('server_url', '')}",
            "",
            "运行目录:",
            *[f"- {key}: {value}" for key, value in paths.items()],
            "",
            "打印组件:",
            *[f"- {item.get('name')}: {'存在' if item.get('exists') else '未发现'} {item.get('path')}" for item in components],
        ]
        text = tk.Text(self, wrap="word")
        text.insert("1.0", "\n".join(lines))
        text.configure(state="disabled")
        text.pack(fill="both", expand=True, padx=12, pady=12)


class AgentWindow(tk.Tk):
    def __init__(self, start_minimized: bool = False):
        super().__init__()
        self.title(f"{OFFICIAL_NAME} v{AGENT_VERSION}")
        self.apply_window_icon()
        self.geometry("700x520")
        self.minsize(660, 500)
        self.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        self.server_status_var = tk.StringVar(value="启动中")
        self.machine_var = tk.StringVar(value="-")
        self.current_status_var = tk.StringVar(value="启动中")
        self.component_var = tk.StringVar(value="未检测")
        self.task_var = tk.StringVar(value="-")
        self.last_upload_time_var = tk.StringVar(value="-")
        self.last_upload_count_var = tk.StringVar(value="-")
        self.detail_var = tk.StringVar(value="正在启动后台心跳")
        self.service_button_var = tk.StringVar(value="停止服务")
        self.controller = AgentRuntimeController(self.schedule_state)
        self.tray = AgentTray(self.status_text, self.show_window, self.reconnect, self.quit_app)
        self.build()
        self.refresh_config_fields()
        self.tray.start()
        self.controller.start()
        if start_minimized:
            self.after(300, self.hide_to_tray)

    def apply_window_icon(self) -> None:
        try:
            ico = icon_path("collector_agent_icon.ico")
            if ico.exists():
                self.iconbitmap(str(ico))
            png = icon_path("collector_agent_icon.png")
            if png.exists():
                self._icon_photo = tk.PhotoImage(file=str(png))
                self.iconphoto(True, self._icon_photo)
        except Exception:
            pass

    def build(self) -> None:
        style = ttk.Style(self)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 16, "bold"))
        style.configure("Value.TLabel", font=("Microsoft YaHei UI", 13, "bold"))
        style.configure("Status.TLabel", font=("Microsoft YaHei UI", 18, "bold"))
        root = ttk.Frame(self, padding=18)
        root.pack(fill="both", expand=True)
        ttk.Label(root, text="打印组件信息采集", style="Title.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(root, text=f"版本 {AGENT_VERSION}", foreground="#64748b").grid(row=0, column=1, sticky="e")

        status = ttk.Frame(root, padding=(0, 16, 0, 8))
        status.grid(row=1, column=0, columnspan=2, sticky="ew")
        ttk.Label(status, textvariable=self.current_status_var, style="Status.TLabel").pack(anchor="w")
        ttk.Label(status, textvariable=self.detail_var, foreground="#64748b", wraplength=620).pack(anchor="w", pady=(4, 0))

        info = ttk.Frame(root)
        info.grid(row=2, column=0, columnspan=2, sticky="nsew", pady=(8, 14))
        rows = [
            ("服务器状态", self.server_status_var),
            ("业务机名称", self.machine_var),
            ("打印组件状态", self.component_var),
            ("当前任务", self.task_var),
            ("最近上传时间", self.last_upload_time_var),
            ("最近上传条数", self.last_upload_count_var),
            ("版本号", tk.StringVar(value=AGENT_VERSION)),
        ]
        for index, (label, var) in enumerate(rows):
            ttk.Label(info, text=label, foreground="#475569").grid(row=index, column=0, sticky="w", pady=7)
            ttk.Label(info, textvariable=var, style="Value.TLabel").grid(row=index, column=1, sticky="w", padx=(24, 0), pady=7)
        info.columnconfigure(1, weight=1)

        actions = ttk.Frame(root)
        actions.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(actions, textvariable=self.service_button_var, command=self.toggle_service).grid(row=0, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text="重新连接", command=self.reconnect).grid(row=0, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text="查看日志", command=open_logs_dir).grid(row=0, column=2, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text="打开设置", command=self.open_settings).grid(row=1, column=0, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text="最小化到托盘", command=self.hide_to_tray).grid(row=1, column=1, sticky="ew", padx=4, pady=4)
        ttk.Button(actions, text="诊断信息", command=self.open_diagnostics).grid(row=1, column=2, sticky="ew", padx=4, pady=4)
        for col in range(3):
            actions.columnconfigure(col, weight=1)
        root.columnconfigure(0, weight=1)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(2, weight=1)

    def refresh_config_fields(self) -> None:
        config = load_config()
        self.machine_var.set(str(config.get("machine_label") or config.get("machine_name") or "-"))

    def schedule_state(self, state: dict[str, Any]) -> None:
        self.after(0, lambda: self.apply_state(state))

    def apply_state(self, state: dict[str, Any]) -> None:
        self.server_status_var.set(str(state.get("server_status") or "-"))
        self.current_status_var.set(str(state.get("current_status") or "-"))
        self.component_var.set(str(state.get("component_text") or self.component_var.get() or "-"))
        self.task_var.set(str(state.get("current_task") or "-"))
        self.detail_var.set(str(state.get("detail") or ""))
        if state.get("last_upload_time"):
            self.last_upload_time_var.set(str(state.get("last_upload_time")))
        if state.get("last_upload_count"):
            self.last_upload_count_var.set(str(state.get("last_upload_count")))
        self.refresh_config_fields()

    def toggle_service(self) -> None:
        if self.controller.enabled:
            self.controller.stop_service()
            self.service_button_var.set("启动服务")
        else:
            self.controller.start()
            self.service_button_var.set("停止服务")

    def reconnect(self) -> None:
        self.service_button_var.set("停止服务")
        self.controller.reconnect_now()
        self.apply_state({"server_status": "重连中", "current_status": "重连中", "current_task": "立即重连", "detail": "正在重新连接 Web 服务"})

    def open_settings(self) -> None:
        SettingsDialog(self)

    def open_diagnostics(self) -> None:
        DiagnosticsDialog(self)

    def after_config_changed(self) -> None:
        self.refresh_config_fields()
        self.controller.reload_config()
        self.apply_state({"server_status": "连接中", "current_status": "重连中", "current_task": "上线注册", "detail": "设置已保存，正在重新连接并注册业务机"})

    def hide_to_tray(self) -> None:
        self.withdraw()
        self.tray.notify("打印组件信息采集仍在运行", "已最小化到系统托盘，后台继续待命。")

    def show_window(self) -> None:
        self.after(0, self._show_window)

    def _show_window(self) -> None:
        self.deiconify()
        self.lift()
        self.focus_force()

    def status_text(self) -> str:
        return self.current_status_var.get() or "-"

    def quit_app(self) -> None:
        self.after(0, self._quit_app)

    def _quit_app(self) -> None:
        self.controller.shutdown()
        self.tray.stop()
        self.destroy()


def run_app(start_minimized: bool = False) -> None:
    runtime_paths_public()
    AgentWindow(start_minimized=start_minimized).mainloop()
