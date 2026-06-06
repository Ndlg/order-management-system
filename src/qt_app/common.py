import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)


ROOT_DIR = Path(__file__).resolve().parents[1]


def resource_path(name):
    base = Path(getattr(sys, "_MEIPASS", ROOT_DIR))
    return base / name


def set_window_icon(window, filename):
    icon_file = resource_path(filename)
    if icon_file.exists():
        window.setWindowIcon(QIcon(str(icon_file)))


def open_path(path):
    path = os.path.abspath(str(path))
    os.makedirs(path, exist_ok=True)
    os.startfile(path)


def open_file_or_folder(path):
    path = os.path.abspath(str(path))
    if os.path.exists(path):
        os.startfile(path)
    else:
        parent = os.path.dirname(path)
        if parent:
            open_path(parent)


def format_bytes(size):
    try:
        value = float(size)
    except Exception:
        value = 0
    units = ["B", "KB", "MB", "GB"]
    for unit in units:
        if value < 1024 or unit == units[-1]:
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return "0 B"


def make_button(text, primary=False, danger=False):
    btn = QPushButton(text)
    if primary:
        btn.setProperty("primary", True)
    if danger:
        btn.setProperty("danger", True)
    return btn


def card(title, value="", subtitle=""):
    frame = QFrame()
    frame.setObjectName("Card")
    frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(14, 12, 14, 12)
    layout.setSpacing(6)

    title_label = QLabel(title)
    title_label.setObjectName("Muted")
    value_label = QLabel(str(value))
    value_label.setStyleSheet("font-size: 24px; font-weight: 800;")
    subtitle_label = QLabel(str(subtitle))
    subtitle_label.setObjectName("Muted")
    subtitle_label.setWordWrap(True)

    layout.addWidget(title_label)
    layout.addWidget(value_label)
    layout.addWidget(subtitle_label)
    return frame, value_label, subtitle_label


def titled_panel(title, content):
    frame = QFrame()
    frame.setObjectName("Card")
    layout = QVBoxLayout(frame)
    layout.setContentsMargins(12, 10, 12, 12)
    layout.setSpacing(8)
    label = QLabel(title)
    label.setObjectName("SectionTitle")
    layout.addWidget(label)
    layout.addWidget(content)
    return frame


def page_header(title, subtitle=""):
    wrapper = QFrame()
    wrapper.setObjectName("PageHeader")
    layout = QVBoxLayout(wrapper)
    layout.setContentsMargins(14, 11, 14, 11)
    layout.setSpacing(2)
    label = QLabel(title)
    label.setObjectName("PageTitle")
    layout.addWidget(label)
    if subtitle:
        sub = QLabel(subtitle)
        sub.setObjectName("Muted")
        layout.addWidget(sub)
    return wrapper


def hbox(*widgets, margins=(0, 0, 0, 0), spacing=8):
    box = QWidget()
    layout = QHBoxLayout(box)
    layout.setContentsMargins(*margins)
    layout.setSpacing(spacing)
    for widget in widgets:
        layout.addWidget(widget)
    return box


def configure_table(table, columns):
    table.setColumnCount(len(columns))
    table.setHorizontalHeaderLabels(columns)
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QTableWidget.SelectRows)
    table.setSelectionMode(QTableWidget.SingleSelection)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setStretchLastSection(True)
    table.setSortingEnabled(False)


def set_table_row(table, row, values):
    table.setRowCount(max(table.rowCount(), row + 1))
    for col, value in enumerate(values):
        item = QTableWidgetItem("" if value is None else str(value))
        item.setFlags(item.flags() ^ Qt.ItemIsEditable)
        table.setItem(row, col, item)


def selected_row(table):
    rows = table.selectionModel().selectedRows()
    return rows[0].row() if rows else -1


def show_error(parent, title, detail):
    QMessageBox.critical(parent, title, str(detail))


def show_info(parent, title, detail):
    QMessageBox.information(parent, title, str(detail))
