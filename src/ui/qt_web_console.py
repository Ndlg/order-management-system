import os
import socket
import sys
import threading
import time
import webbrowser
from datetime import datetime
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPlainTextEdit,
    QSizePolicy,
    QTabWidget,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from utils.app_info import window_title
from utils.order_secure_common import get_data_dir, get_data_file, get_output_dir, image_storage_summary, load_data
from ui.qt_app.common import (
    card,
    configure_table,
    make_button,
    open_path,
    page_header,
    set_table_row,
    set_window_icon,
    show_error,
    titled_panel,
)
from ui.qt_app.theme import apply_app_style
from ui.qt_app.single_instance import SingleInstanceGuard, activate_window


class WebConsoleWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.server = None
        self.server_thread = None
        self.started_at = None
        self.request_rows = []
        self.collector_logs = []
        self.collector_seen = {}

        self.setWindowTitle(window_title("Web服务控制台"))
        self.resize(1040, 820)
        self.setMinimumSize(960, 760)
        set_window_icon(self, "icon_web.ico")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(16, 14, 16, 10)
        layout.setSpacing(10)
        layout.addWidget(page_header("Web服务控制台", "启动本机 FastAPI 服务，供浏览器或局域网设备访问订单整理接口。"))
        layout.addWidget(self._build_config())
        layout.addLayout(self._build_cards())
        layout.addWidget(self._build_request_table())
        layout.addWidget(self._build_collector_panel(), 1)
        layout.addWidget(self._build_info_panel())
        layout.addLayout(self._build_buttons())

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh_status)
        self.timer.start(1000)

        self.refresh_networks()
        self.add_log("控制台已打开")
        self.refresh_status()

    def _build_config(self):
        panel = QWidget()
        grid = QGridLayout(panel)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(10)
        self.host_combo = QComboBox()
        self.port_edit = QLineEdit("8000")
        self.port_edit.setFixedWidth(100)
        refresh = make_button("刷新网卡")
        refresh.clicked.connect(self.refresh_networks)
        grid.addWidget(QLabel("监听地址"), 0, 0)
        grid.addWidget(self.host_combo, 0, 1)
        grid.addWidget(refresh, 0, 2)
        grid.addWidget(QLabel("端口"), 0, 3)
        grid.addWidget(self.port_edit, 0, 4)
        grid.setColumnStretch(1, 1)
        return titled_panel("服务配置", panel)

    def _build_cards(self):
        layout = QGridLayout()
        self.status_value = {}
        for col, (key, title) in enumerate(
            [
                ("state", "服务状态"),
                ("port", "访问端口"),
                ("requests", "今日请求"),
                ("resources", "系统资源"),
            ]
        ):
            frame, value, sub = card(title, "-", "")
            self.status_value[key] = (value, sub)
            layout.addWidget(frame, 0, col)
        return layout

    def _build_request_table(self):
        self.request_table = QTableWidget()
        configure_table(self.request_table, ["时间", "客户端IP", "请求路径", "状态", "耗时"])
        self.request_table.setMinimumHeight(56)
        self.request_table.setMaximumHeight(78)
        panel = titled_panel("实时访问日志", self.request_table)
        panel.setMaximumHeight(122)
        return panel

    def _build_collector_panel(self):
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        grid = QGridLayout()
        grid.setHorizontalSpacing(14)
        grid.setVerticalSpacing(4)
        self.collector_value = {}
        for col, (key, title) in enumerate(
            [
                ("clients", "采集客户端"),
                ("online", "在线客户端"),
                ("batch", "监听批次"),
                ("uploads", "上传状态"),
            ]
        ):
            value = QLabel("-")
            value.setObjectName("StatValue")
            sub = QLabel(title)
            sub.setObjectName("Muted")
            box = QVBoxLayout()
            box.setContentsMargins(0, 0, 0, 0)
            box.addWidget(value)
            box.addWidget(sub)
            grid.addLayout(box, 0, col)
            self.collector_value[key] = (value, sub)
        layout.addLayout(grid)

        controls = QHBoxLayout()
        self.collector_refresh_btn = make_button("刷新客户端")
        self.admin_btn = make_button("打开订单整理系统")
        self.collector_refresh_btn.clicked.connect(lambda: self.refresh_collector_status(self.is_running()))
        self.admin_btn.clicked.connect(self.open_admin_app)
        controls.addWidget(self.collector_refresh_btn)
        controls.addWidget(self.admin_btn)
        grid.addLayout(controls, 0, 4)
        grid.setColumnStretch(4, 1)

        self.collector_table = QTableWidget()
        configure_table(self.collector_table, ["业务机", "状态", "组件", "上传", "最后心跳"])
        self.collector_table.setMinimumHeight(90)
        self.collector_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.collector_log_table = QTableWidget()
        configure_table(self.collector_log_table, ["时间", "类型", "客户端", "内容"])
        self.collector_log_table.setMinimumHeight(90)
        self.collector_log_table.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        self.collector_tabs = QTabWidget()
        self.collector_tabs.addTab(self.collector_table, "客户端")
        self.collector_tabs.addTab(self.collector_log_table, "连接日志")
        self.collector_tabs.setMinimumHeight(128)
        self.collector_tabs.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        layout.addWidget(self.collector_tabs, 1)

        frame = titled_panel("采集工具客户端连接", panel)
        frame.setMinimumHeight(245)
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        return frame

    def _build_info_panel(self):
        self.info_box = QPlainTextEdit()
        self.info_box.setReadOnly(True)
        self.info_box.setMinimumHeight(54)
        self.info_box.setMaximumHeight(72)
        panel = titled_panel("系统信息", self.info_box)
        panel.setMaximumHeight(116)
        return panel

    def _build_buttons(self):
        layout = QHBoxLayout()
        self.start_btn = make_button("打开服务", primary=True)
        self.stop_btn = make_button("停止服务", danger=True)
        self.restart_btn = make_button("重启服务")
        self.browser_btn = make_button("打开网页")
        self.docs_btn = make_button("打开接口文档")
        self.output_btn = make_button("打开输出目录")
        self.start_btn.clicked.connect(self.start_service)
        self.stop_btn.clicked.connect(self.stop_service)
        self.restart_btn.clicked.connect(self.restart_service)
        self.browser_btn.clicked.connect(lambda: webbrowser.open(self.base_url()))
        self.docs_btn.clicked.connect(lambda: webbrowser.open(self.base_url("/docs")))
        self.output_btn.clicked.connect(lambda: open_path(get_output_dir()))
        for btn in [self.start_btn, self.stop_btn, self.restart_btn, self.browser_btn, self.docs_btn, self.output_btn]:
            layout.addWidget(btn)
        layout.addStretch(1)
        return layout

    def refresh_networks(self):
        current = self.host_combo.currentData()
        self.host_combo.clear()
        self.host_combo.addItem("0.0.0.0 - 所有网卡", "0.0.0.0")
        self.host_combo.addItem("127.0.0.1 - 仅本机", "127.0.0.1")
        for ip in self.local_ips():
            if ip not in {"127.0.0.1"}:
                self.host_combo.addItem(f"{ip} - 局域网", ip)
        if current:
            idx = self.host_combo.findData(current)
            if idx >= 0:
                self.host_combo.setCurrentIndex(idx)

    def local_ips(self):
        ips = set()
        try:
            name = socket.gethostname()
            for item in socket.getaddrinfo(name, None, socket.AF_INET):
                ips.add(item[4][0])
        except Exception:
            pass
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.connect(("8.8.8.8", 80))
            ips.add(sock.getsockname()[0])
            sock.close()
        except Exception:
            pass
        return sorted(ip for ip in ips if ip and not ip.startswith("169.254."))

    def selected_host(self):
        return self.host_combo.currentData() or "127.0.0.1"

    def selected_port(self):
        try:
            return int(self.port_edit.text().strip() or "8000")
        except ValueError:
            return 8000

    def display_host(self):
        host = self.selected_host()
        if host == "0.0.0.0":
            ips = [ip for ip in self.local_ips() if not ip.startswith("127.")]
            return ips[0] if ips else "127.0.0.1"
        return host

    def base_url(self, suffix=""):
        return f"http://{self.display_host()}:{self.selected_port()}{suffix}"

    def start_service(self):
        if self.is_running():
            self.add_log("服务已经在运行")
            return
        try:
            import uvicorn
            from ui.app import app as fastapi_app

            config = uvicorn.Config(
                fastapi_app,
                host=self.selected_host(),
                port=self.selected_port(),
                log_level="warning",
                access_log=False,
                log_config=None,
            )
            self.server = uvicorn.Server(config)
            self.server_thread = threading.Thread(target=self.server.run, daemon=True)
            self.server_thread.start()
            self.started_at = datetime.now()
            self.add_log(f"服务启动中：{self.base_url()}")
        except Exception as exc:
            show_error(self, "服务启动失败", exc)
            self.server = None
            self.server_thread = None

    def stop_service(self):
        if not self.server:
            self.add_log("服务未启动")
            return
        self.server.should_exit = True
        self.add_log("已发送停止服务指令")

    def restart_service(self):
        self.stop_service()
        QTimer.singleShot(1200, self.start_service)

    def is_running(self):
        return bool(self.server_thread and self.server_thread.is_alive() and self.server and self.server.started)

    def add_collector_log(self, kind, client, message):
        self.collector_logs.insert(0, (datetime.now().strftime("%H:%M:%S"), kind, client, message))
        self.collector_logs = self.collector_logs[:80]
        self.collector_log_table.setRowCount(0)
        for row, values in enumerate(self.collector_logs):
            set_table_row(self.collector_log_table, row, values)
        self.statusBar().showMessage(message)

    def refresh_status(self):
        running = self.is_running()
        if self.server and self.server_thread and not self.server_thread.is_alive() and not running:
            self.server = None
            self.server_thread = None
            self.add_log("服务已停止")

        self.status_value["state"][0].setText("运行中" if running else "未启动")
        self.status_value["state"][1].setText(
            f"启动时间：{self.started_at.strftime('%Y-%m-%d %H:%M:%S')}" if running and self.started_at else "等待启动"
        )
        self.status_value["port"][0].setText(str(self.selected_port()))
        self.status_value["port"][1].setText(self.base_url())
        self.status_value["requests"][0].setText(str(len(self.request_rows)))
        self.status_value["requests"][1].setText("本控制台记录")
        self.status_value["resources"][0].setText(sys.version.split()[0])
        self.status_value["resources"][1].setText("Python / Uvicorn")

        self.start_btn.setEnabled(not running)
        self.stop_btn.setEnabled(running)
        self.restart_btn.setEnabled(True)
        self.refresh_collector_status(running)
        self.update_info()
        self.statusBar().showMessage("服务运行正常" if running else "服务未启动")

    def refresh_collector_status(self, server_running):
        payload = self.collector_status_payload()
        collectors = payload.get("collectors", [])
        online = [item for item in collectors if item.get("online")]
        uploaded = payload.get("uploaded_collectors", 0)
        batch_id = payload.get("batch_id", "")
        status_text = payload.get("status", "idle")

        self.collector_value["clients"][0].setText(str(len(collectors)))
        self.collector_value["clients"][1].setText("已连接过")
        self.collector_value["online"][0].setText(str(len(online)))
        self.collector_value["online"][1].setText("当前在线")
        self.collector_value["batch"][0].setText(status_text)
        self.collector_value["batch"][1].setText(batch_id or "无活动批次")
        self.collector_value["uploads"][0].setText(f"{uploaded}/{len(collectors)}")
        self.collector_value["uploads"][1].setText("已上传 / 客户端")

        self.collector_refresh_btn.setEnabled(server_running)
        self.update_collector_logs(collectors)

        self.collector_table.setRowCount(0)
        for row, item in enumerate(collectors):
            component_text = f"{item.get('available_components', 0)}/{item.get('component_count', 0)}"
            upload_text = f"{item.get('uploaded_records', 0)}条" if item.get("uploaded") else "未上传"
            set_table_row(
                self.collector_table,
                row,
                [
                    item.get("machine_label") or item.get("client_id", ""),
                    "在线" if item.get("online") else "离线",
                    component_text,
                    upload_text,
                    item.get("last_seen") or item.get("uploaded_at") or "",
                ],
            )

    def collector_status_payload(self):
        if not self.is_running():
            return {"status": "idle", "batch_id": "", "collectors": [], "uploaded_collectors": 0}
        try:
            from ui import app as web_app

            return web_app.waybill_status_payload()
        except Exception as exc:
            return {"status": "error", "batch_id": "", "collectors": [], "uploaded_collectors": 0, "error": str(exc)}

    def update_collector_logs(self, collectors):
        current = {}
        for item in collectors:
            client = item.get("client_id") or item.get("machine_label") or ""
            if not client:
                continue
            state = {
                "online": bool(item.get("online")),
                "uploaded_records": int(item.get("uploaded_records") or 0),
                "last_seen": item.get("last_seen") or "",
                "components": f"{item.get('available_components', 0)}/{item.get('component_count', 0)}",
            }
            previous = self.collector_seen.get(client)
            label = item.get("machine_label") or client
            if previous is None:
                self.add_collector_log("连接", label, f"客户端注册，组件 {state['components']}")
            else:
                if state["online"] and not previous.get("online"):
                    self.add_collector_log("上线", label, "客户端恢复在线")
                if not state["online"] and previous.get("online"):
                    self.add_collector_log("离线", label, "客户端心跳超时")
                if state["uploaded_records"] > previous.get("uploaded_records", 0):
                    self.add_collector_log("上传", label, f"上传 {state['uploaded_records']} 条打印信息")
            current[client] = state
        self.collector_seen = current

    def open_admin_app(self):
        exe = os.path.join(os.path.dirname(os.path.abspath(sys.executable if getattr(sys, "frozen", False) else __file__)), "订单整理管理系统.exe")
        if os.path.exists(exe):
            os.startfile(exe)
        else:
            show_error(self, "未找到订单整理系统", exe)

    def update_info(self):
        try:
            data = load_data(auto_save_on_read=False)
            systems = len(data.get("systems", {})) if isinstance(data, dict) else 0
        except Exception:
            systems = 0
        stats = image_storage_summary(count_entries=False)
        self.info_box.setPlainText(
            f"数据文件：{get_data_file()}\n"
            f"数据目录：{get_data_dir()}\n"
            f"输出目录：{get_output_dir()}\n"
            f"系统数量：{systems}\n"
            f"图片文件：{stats.get('image_files', 0)} 个 / 图片鞋款分类：{stats.get('category_files', 0)} 个"
        )

    def add_log(self, message, path="/", status="待机", cost="-"):
        now = datetime.now().strftime("%H:%M:%S")
        self.request_rows.insert(0, (now, "127.0.0.1", path, status, cost))
        self.request_rows = self.request_rows[:80]
        self.request_table.setRowCount(0)
        for row, values in enumerate(self.request_rows):
            set_table_row(self.request_table, row, values)
        self.statusBar().showMessage(message)

    def closeEvent(self, event):
        if self.server:
            self.server.should_exit = True
        super().closeEvent(event)


def main():
    if "--self-test" in sys.argv or "--self-test-web" in sys.argv:
        sys.exit(service_config_self_test())

    app = QApplication(sys.argv)
    apply_app_style(app)
    guard = SingleInstanceGuard("web-console", app)
    if not guard.start_or_notify():
        sys.exit(0)
    window = WebConsoleWindow()
    guard.activated.connect(lambda: activate_window(window))
    window.show()
    sys.exit(app.exec())


def service_config_self_test():
    try:
        import uvicorn
        from ui.app import app as fastapi_app

        config = uvicorn.Config(
            fastapi_app,
            host="127.0.0.1",
            port=8879,
            log_level="warning",
            access_log=False,
            log_config=None,
        )
        uvicorn.Server(config)
        return 0
    except Exception:
        return 1


if __name__ == "__main__":
    main()
