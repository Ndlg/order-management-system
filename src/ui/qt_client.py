import os
import sys
from datetime import datetime
from pathlib import Path

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QProgressBar,
    QSplitter,
    QTableWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from core.order_core import generate_order_file
from utils.app_info import window_title
from utils.order_secure_common import get_active_system, get_output_dir, load_data, load_templates_fast
from ui.qt_app.common import (
    configure_table,
    make_button,
    open_file_or_folder,
    open_path,
    page_header,
    set_table_row,
    set_window_icon,
    show_error,
    show_info,
    titled_panel,
)
from ui.qt_app.theme import apply_app_style
from ui.qt_app.single_instance import SingleInstanceGuard, activate_window
from ui.qt_app.workers import TaskWorker


class ClientWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.files = []
        self.worker = None
        self.output_path = ""

        self.setWindowTitle(window_title("一键整理订单"))
        self.resize(1180, 760)
        self.setMinimumSize(980, 640)
        set_window_icon(self, "icon_frontend.ico")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QVBoxLayout(root)
        layout.setContentsMargins(14, 14, 14, 10)
        layout.setSpacing(10)

        layout.addWidget(page_header("一键整理订单", "导入订单 Excel 后先统一成五字段，再按鞋款分类、鞋款档口和图片关系生成整理文件。"))
        layout.addLayout(self._build_steps())
        layout.addWidget(self._build_import_panel())

        splitter = QSplitter(Qt.Horizontal)
        splitter.addWidget(self._build_file_panel())
        splitter.addWidget(self._build_log_panel())
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        bottom = QHBoxLayout()
        self.clear_btn = make_button("清空列表")
        self.open_output_btn = make_button("打开输出目录")
        self.generate_btn = make_button("一键生成订单", primary=True)
        self.clear_btn.clicked.connect(self.clear_files)
        self.open_output_btn.clicked.connect(lambda: open_path(get_output_dir()))
        self.generate_btn.clicked.connect(self.generate)
        bottom.addWidget(self.clear_btn)
        bottom.addWidget(self.open_output_btn)
        bottom.addStretch(1)
        bottom.addWidget(self.generate_btn)
        layout.addLayout(bottom)

        self.statusBar().showMessage("就绪")
        self.refresh_templates()
        self.log("等待导入订单 Excel")

    def _build_steps(self):
        layout = QGridLayout()
        layout.setHorizontalSpacing(8)
        labels = ["1 选择模板", "2 导入数据", "3 处理订单", "4 生成完成"]
        for idx, text in enumerate(labels):
            label = QLabel(text)
            label.setAlignment(Qt.AlignCenter)
            label.setStyleSheet(
                "padding: 8px; border-radius: 6px; background: #ffffff; border: 1px solid #d9e1ea;"
                + ("color: white; background: #0f9d8a; font-weight: 700;" if idx == 0 else "")
            )
            layout.addWidget(label, 0, idx)
        return layout

    def _build_import_panel(self):
        panel = QWidget()
        layout = QGridLayout(panel)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setHorizontalSpacing(10)
        layout.setVerticalSpacing(8)

        self.template_combo = QComboBox()
        self.output_mode_combo = QComboBox()
        self.output_mode_combo.addItem("按鞋款档口分Sheet", "按档口分Sheet")
        self.output_mode_combo.addItem("合并一个Sheet", "合并一个Sheet")
        self.output_mode_combo.addItem("按鞋款档口分文档", "按档口分文档")
        self.choose_btn = make_button("选择订单 Excel", primary=True)
        self.refresh_btn = make_button("刷新模板")
        self.choose_btn.clicked.connect(self.choose_files)
        self.refresh_btn.clicked.connect(self.refresh_templates)

        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setValue(0)

        layout.addWidget(QLabel("导入模板"), 0, 0)
        layout.addWidget(self.template_combo, 0, 1)
        layout.addWidget(self.refresh_btn, 0, 2)
        layout.addWidget(QLabel("输出方式"), 0, 3)
        layout.addWidget(self.output_mode_combo, 0, 4)
        layout.addWidget(self.choose_btn, 0, 5)
        layout.addWidget(QLabel("处理进度"), 1, 0)
        layout.addWidget(self.progress, 1, 1, 1, 5)
        return titled_panel("订单 Excel", panel)

    def _build_file_panel(self):
        self.file_table = QTableWidget()
        configure_table(self.file_table, ["序号", "文件名", "大小", "修改时间", "完整路径"])
        self.file_table.setColumnWidth(0, 58)
        self.file_table.setColumnWidth(1, 240)
        self.file_table.setColumnWidth(2, 90)
        self.file_table.setColumnWidth(3, 150)
        return titled_panel("订单明细（预览）", self.file_table)

    def _build_log_panel(self):
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        return titled_panel("处理日志", self.log_box)

    def refresh_templates(self):
        current = self.template_combo.currentText()
        self.template_combo.clear()
        names = [t.get("name", "") for t in load_templates_fast() if isinstance(t, dict) and t.get("name")]
        self.template_combo.addItems(names or ["1688新版-表头模式"])
        if current:
            idx = self.template_combo.findText(current)
            if idx >= 0:
                self.template_combo.setCurrentIndex(idx)
        self.log(f"模板已刷新：{self.template_combo.count()} 个")

    def choose_files(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择订单 Excel",
            "",
            "Excel 文件 (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if not files:
            return
        existing = set(self.files)
        for file in files:
            if file not in existing:
                self.files.append(file)
        self.render_files()
        self.progress.setValue(0)
        self.log(f"已加入 {len(files)} 个文件")

    def clear_files(self):
        self.files = []
        self.output_path = ""
        self.file_table.setRowCount(0)
        self.progress.setValue(0)
        self.log("文件列表已清空")

    def render_files(self):
        self.file_table.setRowCount(0)
        for idx, path in enumerate(self.files, start=1):
            try:
                stat = os.stat(path)
                size = f"{stat.st_size / 1024:.1f} KB"
                mtime = datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M")
            except OSError:
                size = "-"
                mtime = "-"
            set_table_row(self.file_table, idx - 1, [idx, os.path.basename(path), size, mtime, path])

    def generate(self):
        if not self.files:
            show_info(self, "缺少文件", "请先选择一个或多个订单 Excel。")
            return

        template_name = self.template_combo.currentText().strip()
        output_mode = self.output_mode_combo.currentData() or self.output_mode_combo.currentText()

        def task():
            data = load_data(auto_save_on_read=False)
            system, _ = get_active_system(data)
            return generate_order_file(self.files, system, output_mode=output_mode, template_name=template_name)

        self.progress.setValue(8)
        self.generate_btn.setEnabled(False)
        self.choose_btn.setEnabled(False)
        self.statusBar().showMessage("正在处理订单...")
        self.log(f"开始处理：{len(self.files)} 个文件 / 模板：{template_name} / 输出：{output_mode}")

        self.worker = TaskWorker(task, self)
        self.worker.finished_ok.connect(self.on_generated)
        self.worker.failed.connect(self.on_failed)
        self.worker.start()

    def on_generated(self, out_path):
        self.output_path = str(out_path)
        self.progress.setValue(100)
        self.generate_btn.setEnabled(True)
        self.choose_btn.setEnabled(True)
        self.statusBar().showMessage("生成完成")
        self.log(f"生成完成：{out_path}")
        show_info(self, "生成完成", f"订单文件已生成：\n{out_path}")
        open_file_or_folder(out_path)

    def on_failed(self, detail):
        self.progress.setValue(0)
        self.generate_btn.setEnabled(True)
        self.choose_btn.setEnabled(True)
        self.statusBar().showMessage("生成失败")
        self.log("生成失败，详情已弹窗显示")
        show_error(self, "生成失败", detail)

    def log(self, message):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.append(f"[{ts}] {message}")


def main():
    app = QApplication(sys.argv)
    apply_app_style(app)
    guard = SingleInstanceGuard("client", app)
    if not guard.start_or_notify():
        sys.exit(0)
    window = ClientWindow()
    guard.activated.connect(lambda: activate_window(window))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
