from PySide6.QtGui import QColor, QPalette


ACCENT = "#128977"
ACCENT_DARK = "#0c655a"
DANGER = "#d9483b"
TEXT = "#182433"
MUTED = "#687789"
BORDER = "#d8e0e8"
PANEL = "#ffffff"
BG = "#f1f4f8"


APP_QSS = f"""
* {{
    font-family: "Microsoft YaHei UI", "Segoe UI", Arial;
    font-size: 13px;
    color: {TEXT};
}}
QMainWindow, QWidget {{
    background: {BG};
}}
QLabel {{
    background: transparent;
}}
QFrame#Sidebar {{
    background: #fbfcfe;
    border-right: 1px solid {BORDER};
}}
QFrame#BrandBlock {{
    background: #f6f9fb;
    border-bottom: 1px solid #dde6ee;
}}
QFrame#PageHeader {{
    background: #f8fbfd;
    border: 1px solid #dce5ed;
    border-radius: 8px;
}}
QLabel#AppTitle {{
    font-size: 16px;
    font-weight: 700;
    color: #101a28;
}}
QLabel#PageTitle {{
    font-size: 19px;
    font-weight: 700;
    color: #101a28;
}}
QLabel#SectionTitle {{
    font-weight: 700;
    color: #223044;
}}
QLabel#Muted {{
    color: {MUTED};
}}
QFrame#Card {{
    background: {PANEL};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}
QFrame#EditorHint {{
    background: #f8fbfc;
    border: 1px solid #dbe7ec;
    border-radius: 8px;
}}
QFrame#EditorForm {{
    background: #ffffff;
    border: 1px solid #dbe3eb;
    border-radius: 8px;
}}
QLabel#EditorTitle {{
    font-size: 15px;
    font-weight: 700;
    color: #142235;
}}
QLabel#EditorState {{
    font-weight: 700;
    color: {ACCENT_DARK};
}}
QFrame#ImagePreview {{
    background: #f8fbfc;
    border: 1px dashed #a9bac8;
    border-radius: 8px;
}}
QFrame#ImagePreview:hover {{
    background: #eef7f5;
    border-color: {ACCENT};
}}
QPushButton {{
    min-height: 30px;
    padding: 5px 15px;
    border: 1px solid #cbd6e2;
    border-radius: 6px;
    background: #fbfdff;
}}
QPushButton:hover {{
    background: #eef7f5;
    border-color: #9dcfc7;
}}
QPushButton:pressed {{
    background: #dcefeb;
}}
QPushButton[primary="true"] {{
    color: white;
    background: {ACCENT};
    border-color: {ACCENT_DARK};
    font-weight: 700;
}}
QPushButton[primary="true"]:hover {{
    background: #12ad99;
}}
QPushButton[danger="true"] {{
    color: white;
    background: {DANGER};
    border-color: #b9362b;
    font-weight: 700;
}}
QPushButton[danger="true"]:hover {{
    background: #e6584b;
}}
QLineEdit, QComboBox, QTextEdit, QPlainTextEdit, QSpinBox {{
    min-height: 28px;
    padding: 4px 8px;
    border: 1px solid #cbd6e2;
    border-radius: 5px;
    background: #ffffff;
}}
QLineEdit:focus, QComboBox:focus, QTextEdit:focus, QPlainTextEdit:focus {{
    border: 1px solid {ACCENT};
}}
QComboBox::drop-down {{
    width: 24px;
    border: 0;
}}
QTableWidget {{
    background: #ffffff;
    alternate-background-color: #f7fafc;
    gridline-color: #e7edf3;
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: #d9f0eb;
    selection-color: {TEXT};
}}
QHeaderView::section {{
    background: #edf3f7;
    color: #354253;
    border: 0;
    border-right: 1px solid #d7e0e8;
    border-bottom: 1px solid #d7e0e8;
    padding: 7px 8px;
    font-weight: 700;
}}
QProgressBar {{
    height: 10px;
    border: 1px solid {BORDER};
    border-radius: 6px;
    background: #edf3f8;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{
    border-radius: 6px;
    background: {ACCENT};
}}
QListWidget {{
    background: transparent;
    border: 0;
    outline: 0;
}}
QListWidget::item {{
    min-height: 36px;
    padding: 6px 10px;
    border-radius: 6px;
    color: #253244;
}}
QListWidget::item:selected {{
    color: {ACCENT_DARK};
    background: #e2f3ef;
    font-weight: 700;
}}
QListWidget::item:selected:hover {{
    color: {ACCENT_DARK};
    background: #d8eee9;
}}
QListWidget::item:hover {{
    color: #182433;
    background: #edf6f3;
}}
QSplitter::handle {{
    background: #e0e7ef;
}}
QStatusBar {{
    background: #ffffff;
    border-top: 1px solid {BORDER};
}}
"""


def apply_app_style(app):
    app.setStyle("Fusion")
    palette = QPalette()
    palette.setColor(QPalette.Window, QColor(BG))
    palette.setColor(QPalette.WindowText, QColor(TEXT))
    palette.setColor(QPalette.Base, QColor("#ffffff"))
    palette.setColor(QPalette.AlternateBase, QColor("#f7fafc"))
    palette.setColor(QPalette.Text, QColor(TEXT))
    palette.setColor(QPalette.Button, QColor("#ffffff"))
    palette.setColor(QPalette.ButtonText, QColor(TEXT))
    palette.setColor(QPalette.Highlight, QColor("#bfe7e1"))
    palette.setColor(QPalette.HighlightedText, QColor(TEXT))
    app.setPalette(palette)
    app.setStyleSheet(APP_QSS)
