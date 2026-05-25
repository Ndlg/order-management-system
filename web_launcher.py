import os
import sys
import time
import socket
import threading
import webbrowser
import traceback
import ctypes
import tkinter as tk
from tkinter import ttk, messagebox

APP_TITLE = "web服务控制台"
WEB_CONSOLE_VERSION = "V7.5.1-LiteData-20260525"


def base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resource_path(filename):
    if getattr(sys, "frozen", False):
        root = getattr(sys, "_MEIPASS", base_dir())
    else:
        root = base_dir()
    return os.path.join(root, filename)


def set_window_icon(root):
    """
    同时修复：
    - 窗口左上角图标
    - 任务栏图标
    - 最小化图标
    """

    try:
        # Windows任务栏图标修复
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
            "order.sorter.web.console"
        )
    except Exception:
        pass

    try:
        ico = resource_path("icon_web.ico")
        if os.path.exists(ico):
            root.iconbitmap(default=ico)
    except Exception:
        pass

    try:
        png = resource_path("icon_web.png")
        if os.path.exists(png):
            img = tk.PhotoImage(file=png)
            root.iconphoto(True, img)
            root._icon_ref = img
    except Exception:
        pass


def get_local_ipv4_addresses():
    """
    自动识别本机可用 IPv4 地址。
    返回格式：
    [
      ("0.0.0.0 - 所有网卡", "0.0.0.0"),
      ("192.168.1.10 - 本机网卡", "192.168.1.10")
    ]
    """
    items = [("0.0.0.0 - 所有网卡", "0.0.0.0"), ("127.0.0.1 - 仅本机", "127.0.0.1")]
    found = set(["0.0.0.0", "127.0.0.1"])

    # 通过主机名获取
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET):
            ip = info[4][0]
            if ip and ip not in found and not ip.startswith("169.254."):
                items.append((f"{ip} - 本机网卡", ip))
                found.add(ip)
    except Exception:
        pass

    # 通过外联 UDP 探测默认出口 IP，不实际发包
    for target in [("8.8.8.8", 80), ("114.114.114.114", 80)]:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(target)
            ip = s.getsockname()[0]
            s.close()

            if ip and ip not in found and not ip.startswith("169.254."):
                items.append((f"{ip} - 默认网络出口", ip))
                found.add(ip)
        except Exception:
            pass

    return items


class WebLauncher:
    def __init__(self, root):
        self.root = root
        self.root.title(f"{APP_TITLE} - {WEB_CONSOLE_VERSION}")
        self.root.geometry("680x340")
        self.root.resizable(False, False)

        self.host_options = get_local_ipv4_addresses()
        self.host_label_to_ip = {label: ip for label, ip in self.host_options}
        self.host_ip_to_label = {ip: label for label, ip in self.host_options}

        self.host = tk.StringVar(value=self.host_ip_to_label.get("0.0.0.0", "0.0.0.0 - 所有网卡"))
        self.port = tk.StringVar(value="8000")
        self.status = tk.StringVar(value="服务未启动")
        self.server = None
        self.server_thread = None
        self.browser_opened = False

        self.build_ui()

    def build_ui(self):
        frame = ttk.LabelFrame(self.root, text="服务配置")
        frame.pack(fill="x", padx=18, pady=16)

        ttk.Label(frame, text="监听地址").grid(row=0, column=0, padx=8, pady=10, sticky="e")

        self.host_combo = ttk.Combobox(
            frame,
            textvariable=self.host,
            values=[label for label, ip in self.host_options],
            width=34,
            state="readonly"
        )
        self.host_combo.grid(row=0, column=1, padx=8, pady=10)

        ttk.Button(frame, text="刷新网卡", command=self.refresh_network_cards).grid(row=0, column=2, padx=8, pady=10)

        ttk.Label(frame, text="端口").grid(row=0, column=3, padx=8, pady=10, sticky="e")
        ttk.Entry(frame, textvariable=self.port, width=12).grid(row=0, column=4, padx=8, pady=10)

        tip = ttk.Label(
            frame,
            text="本机使用 127.0.0.1；局域网多人访问可用 0.0.0.0，并通过本机IP访问。"
        )
        tip.grid(row=1, column=0, columnspan=5, padx=8, pady=(0,10), sticky="w")

        btns = ttk.Frame(self.root)
        btns.pack(fill="x", padx=18, pady=8)

        tk.Button(btns, text="启动服务", command=self.start_service, bg="#1F4E78", fg="white", width=14).pack(side="left", padx=6)
        ttk.Button(btns, text="停止服务", command=self.stop_service, width=14).pack(side="left", padx=6)
        ttk.Button(btns, text="打开浏览器", command=self.open_browser, width=14).pack(side="left", padx=6)

        status_box = ttk.LabelFrame(self.root, text="运行状态")
        status_box.pack(fill="both", expand=True, padx=18, pady=12)

        ttk.Label(status_box, textvariable=self.status, foreground="#1f4e78").pack(anchor="w", padx=12, pady=12)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def get_selected_host_ip(self):
        selected = self.host.get().strip()

        if selected in self.host_label_to_ip:
            return self.host_label_to_ip[selected]

        # 兼容手动值
        if " - " in selected:
            return selected.split(" - ", 1)[0].strip()

        return selected or "0.0.0.0"

    def refresh_network_cards(self):
        current_ip = self.get_selected_host_ip()

        self.host_options = get_local_ipv4_addresses()
        self.host_label_to_ip = {label: ip for label, ip in self.host_options}
        self.host_ip_to_label = {ip: label for label, ip in self.host_options}

        if hasattr(self, "host_combo"):
            self.host_combo["values"] = [label for label, ip in self.host_options]

        # 优先保留当前选择，其次默认0.0.0.0
        if current_ip in self.host_ip_to_label:
            self.host.set(self.host_ip_to_label[current_ip])
        else:
            self.host.set(self.host_ip_to_label.get("0.0.0.0", "0.0.0.0 - 所有网卡"))

    def start_service(self):
        """
        同进程线程启动 uvicorn，避免每次点击都弹出新控制台或新进程。
        """
        if self.server_thread and self.server_thread.is_alive():
            self.status.set(f"服务已在运行\n访问地址：http://{self.get_display_host()}:{self.port.get().strip()}")
            messagebox.showinfo("提示", "服务已经在运行")
            return

        host = self.get_selected_host_ip()
        port = self.port.get().strip()

        try:
            port_int = int(port)
        except Exception:
            messagebox.showerror("错误", "端口必须是数字")
            return

        self.browser_opened = False

        try:
            self.status.set("正在加载Web服务模块...")
            self.root.update_idletasks()

            # 懒加载：控制台窗口先打开，点击启动服务后才加载FastAPI/pandas/openpyxl/PIL等重模块。
            import uvicorn
            from app import app as fastapi_app

            config = uvicorn.Config(
                fastapi_app,
                host=host,
                port=port_int,
                log_level="warning",
                access_log=False,
                reload=False,
                log_config=None
            )
            self.server = uvicorn.Server(config)
        except Exception as e:
            messagebox.showerror("启动失败", str(e))
            self.status.set("服务未启动")
            return

        def run_server():
            try:
                self.server.run()
            except Exception as e:
                err = traceback.format_exc()
                self.root.after(0, lambda: self.status.set(f"服务启动失败：\n{e}"))
                self.root.after(0, lambda: messagebox.showerror("服务异常", err))
            finally:
                if self.server and getattr(self.server, "should_exit", False):
                    self.root.after(0, lambda: self.status.set("服务已停止"))
                elif not (self.server_thread and self.server_thread.is_alive()):
                    self.root.after(0, lambda: self.status.set("服务已停止"))

        self.server_thread = threading.Thread(target=run_server, daemon=True)
        self.server_thread.start()

        self.status.set(f"服务启动中...\n访问地址：http://{self.get_display_host()}:{port}")

        def delayed_open():
            time.sleep(1.2)
            if self.server_thread and self.server_thread.is_alive() and self.server and getattr(self.server, "started", False):
                self.status.set(f"服务运行中\n访问地址：http://{self.get_display_host()}:{port}")
                if not self.browser_opened:
                    self.browser_opened = True
                    self.open_browser()
            elif self.server_thread and self.server_thread.is_alive():
                self.status.set("服务仍在启动中，请稍候...")
            else:
                self.status.set("服务启动失败或已停止，请查看错误提示")

        threading.Thread(target=delayed_open, daemon=True).start()

    def stop_service(self):
        if not self.server_thread or not self.server_thread.is_alive():
            self.status.set("服务未启动")
            return

        try:
            if self.server:
                self.server.should_exit = True
        except Exception:
            pass

        self.status.set("正在停止服务...")

        def wait_stop():
            try:
                if self.server_thread:
                    self.server_thread.join(timeout=3)
            except Exception:
                pass
            self.root.after(0, lambda: self.status.set("服务已停止"))

        threading.Thread(target=wait_stop, daemon=True).start()

    def get_display_host(self):
        host = self.get_selected_host_ip()
        if host == "0.0.0.0":
            # 浏览器本机访问仍使用127.0.0.1；局域网其他电脑用本机网卡IP访问
            return "127.0.0.1"
        return host

    def open_browser(self):
        port = self.port.get().strip()
        webbrowser.open(f"http://{self.get_display_host()}:{port}")

    def on_close(self):
        try:
            if self.server:
                self.server.should_exit = True
            if self.server_thread and self.server_thread.is_alive():
                self.server_thread.join(timeout=1.5)
        except Exception:
            pass
        self.root.destroy()


def main():
    root = tk.Tk()
    set_window_icon(root)
    WebLauncher(root)
    root.mainloop()


if __name__ == "__main__":
    main()
