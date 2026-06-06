# -*- coding: utf-8 -*-
from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox

from . import agent_db_reader
from .agent_auth import bind_with_code
from .agent_config import load_config, runtime_paths_public, save_config
from .agent_models import AGENT_VERSION, OFFICIAL_NAME, PROTOCOL_VERSION
from .agent_service import CollectorAgentService
from .agent_tray import open_data_dir, open_logs_dir


class AgentWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{OFFICIAL_NAME} v{AGENT_VERSION}")
        self.geometry("640x460")
        self.resizable(True, True)
        self.config_data = load_config()
        self.service_thread: threading.Thread | None = None
        self.status_var = tk.StringVar(value="服务未启动")
        self.component_var = tk.StringVar(value="未检测")
        self.last_upload_var = tk.StringVar(value="-")
        self.build()
        self.refresh_fields()

    def build(self) -> None:
        pad = {"padx": 10, "pady": 6}
        frame = tk.Frame(self)
        frame.pack(fill="both", expand=True, padx=12, pady=12)

        self.server_entry = self.row(frame, "服务器地址", 0)
        self.bind_entry = self.row(frame, "绑定码/账号", 1)
        self.machine_name_entry = self.row(frame, "machine_name", 2)
        self.machine_label_entry = self.row(frame, "machine_label", 3)

        labels = [
            ("连接状态", self.status_var),
            ("打印组件状态", self.component_var),
            ("当前批次", tk.StringVar(value="-")),
            ("当前状态", self.status_var),
            ("最近上传时间", self.last_upload_var),
            ("最近上传条数", tk.StringVar(value="-")),
            ("agent_version", tk.StringVar(value=AGENT_VERSION)),
            ("protocol_version", tk.StringVar(value=PROTOCOL_VERSION)),
        ]
        for index, (name, var) in enumerate(labels, 4):
            tk.Label(frame, text=name, anchor="w", width=16).grid(row=index, column=0, sticky="w", **pad)
            tk.Label(frame, textvariable=var, anchor="w").grid(row=index, column=1, sticky="ew", **pad)

        buttons = tk.Frame(frame)
        buttons.grid(row=12, column=0, columnspan=2, sticky="ew", padx=10, pady=12)
        tk.Button(buttons, text="连接/重新绑定", command=self.bind).pack(side="left", padx=4)
        tk.Button(buttons, text="立即检测", command=self.check_components).pack(side="left", padx=4)
        tk.Button(buttons, text="同步状态", command=self.sync_once).pack(side="left", padx=4)
        tk.Button(buttons, text="查看日志", command=open_logs_dir).pack(side="left", padx=4)
        tk.Button(buttons, text="打开数据目录", command=open_data_dir).pack(side="left", padx=4)
        tk.Button(buttons, text="退出", command=self.destroy).pack(side="right", padx=4)
        frame.columnconfigure(1, weight=1)

    def row(self, frame: tk.Frame, label: str, row: int) -> tk.Entry:
        tk.Label(frame, text=label, anchor="w", width=16).grid(row=row, column=0, sticky="w", padx=10, pady=6)
        entry = tk.Entry(frame)
        entry.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        return entry

    def refresh_fields(self) -> None:
        self.config_data = load_config()
        for entry, key in (
            (self.server_entry, "server_url"),
            (self.machine_name_entry, "machine_name"),
            (self.machine_label_entry, "machine_label"),
        ):
            entry.delete(0, tk.END)
            entry.insert(0, str(self.config_data.get(key) or ""))
        self.status_var.set("已绑定" if self.config_data.get("agent_token") else "未绑定")

    def save_entries(self) -> None:
        self.config_data.update(
            {
                "server_url": self.server_entry.get().strip(),
                "machine_name": self.machine_name_entry.get().strip(),
                "machine_label": self.machine_label_entry.get().strip(),
            }
        )
        self.config_data = save_config(self.config_data)

    def bind(self) -> None:
        try:
            self.save_entries()
            bind_text = self.bind_entry.get().strip()
            config = bind_with_code(self.config_data["server_url"], bind_text, self.machine_label_entry.get().strip(), bind_text if "@" in bind_text else "")
            self.config_data = config
            self.status_var.set("已连接")
            messagebox.showinfo(OFFICIAL_NAME, "绑定成功")
        except Exception as exc:
            self.status_var.set("绑定失败")
            messagebox.showerror(OFFICIAL_NAME, str(exc))

    def check_components(self) -> None:
        status = agent_db_reader.component_status()
        ok = len([item for item in status if item.get("exists")])
        self.component_var.set(f"可用 {ok}/{len(status)}")

    def sync_once(self) -> None:
        try:
            self.save_entries()
            response = CollectorAgentService(self.config_data).sync_once()
            self.status_var.set(f"已同步：{response.get('command', 'idle')}")
        except Exception as exc:
            self.status_var.set("同步失败")
            messagebox.showerror(OFFICIAL_NAME, str(exc))


def run_app() -> None:
    runtime_paths_public()
    AgentWindow().mainloop()
