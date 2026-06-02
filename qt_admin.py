import os
import re
from pathlib import Path
import sys
import zipfile
from datetime import datetime
from types import SimpleNamespace
from xml.etree import ElementTree as ET

import pandas as pd
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from app_info import APP_EDITION, APP_NAME, APP_VERSION, display_version
from order_secure_common import (
    backup_data_file,
    delete_image_binding,
    get_active_system,
    get_data_dir,
    get_data_file,
    get_image_category_dir,
    get_images_dir,
    get_output_dir,
    image_storage_summary,
    ImageMatcher,
    iter_image_bindings,
    list_image_category_names,
    load_image_map_for_categories,
    load_data,
    normalize_image_aliases,
    normalize_text,
    preview_data_summary,
    save_data,
    save_templates_fast,
    update_image_binding,
    upsert_image_binding,
)
from waybill_raw_contract import (
    LEGACY_WAYBILL_REMARK_FIELD,
    RAW_PIPELINE_INTERNAL_FIELDS,
    RAW_WAYBILL_MODE,
    RAW_WAYBILL_TEXT_COLUMN,
    WAYBILL_IMAGE_STATUS_FIELD,
)
from waybill_raw_pipeline import parse_raw_waybill_dataframe, write_processed_waybill_xlsx
from waybill_text_parser import (
    infer_shoe_from_shop_keyword,
    infer_shoe_from_spec,
    normalize_qty,
    normalize_rule_config,
    parse_waybill_raw_text,
    strip_rule_shoe_prefix,
)
from qt_app.common import (
    card,
    configure_table,
    make_button,
    open_file_or_folder,
    open_path,
    page_header,
    selected_row,
    set_table_row,
    set_window_icon,
    show_error,
    show_info,
    titled_panel,
)
from qt_app.theme import apply_app_style
from qt_app.single_instance import SingleInstanceGuard, activate_window
from sku_image_binder import (
    DEFAULT_MAX_IMAGE_MB,
    DEFAULT_TIMEOUT,
    create_template as create_sku_image_template_file,
    import_bindings as import_sku_image_bindings_file,
    missing_report as create_missing_image_report_file,
)


class ImageDropPreview(QFrame):
    fileSelected = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self.setMinimumHeight(260)
        self.setObjectName("ImagePreview")
        self._pixmap = QPixmap()
        self._text = "无图片\n点击选择，或把图片拖到这里"

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        self.label = QLabel(self._text)
        self.label.setAlignment(Qt.AlignCenter)
        self.label.setWordWrap(True)
        self.label.setStyleSheet("color: #6f7c8b;")
        layout.addWidget(self.label, 1)

    def set_image(self, path="", fallback_text=""):
        self._pixmap = QPixmap()
        if path and os.path.exists(path):
            pixmap = QPixmap(path)
            if not pixmap.isNull():
                self._pixmap = pixmap
                self._text = fallback_text or os.path.basename(path)
                self._refresh_pixmap()
                return
        self._text = fallback_text or "无图片\n点击选择，或把图片拖到这里"
        self.label.setPixmap(QPixmap())
        self.label.setText(self._text)

    def _refresh_pixmap(self):
        if self._pixmap.isNull():
            return
        available = self.label.size()
        scaled = self._pixmap.scaled(
            available.width(),
            available.height(),
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.label.setPixmap(scaled)
        self.label.setText("")

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._refresh_pixmap()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.pick_file()
        super().mouseReleaseEvent(event)

    def dragEnterEvent(self, event):
        if self._event_image_file(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._event_image_file(event)
        if path:
            self.fileSelected.emit(path)
            event.acceptProposedAction()
        else:
            event.ignore()

    def pick_file(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*.*)",
        )
        if file:
            self.fileSelected.emit(file)

    def _event_image_file(self, event):
        mime = event.mimeData()
        if not mime.hasUrls():
            return ""
        for url in mime.urls():
            path = url.toLocalFile()
            if self._is_image_file(path):
                return path
        return ""

    def _is_image_file(self, path):
        return os.path.isfile(path) and os.path.splitext(path)[1].lower() in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".bmp",
        }


class AdminWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.data = {}
        self.system = {}
        self.system_id = "default"
        self.current_image = None
        self.pending_image_path = ""
        self.waybill_parse_source_file = ""
        self.waybill_parse_saved_file = ""
        self.waybill_parse_rule_index = []

        self.setWindowTitle(APP_NAME)
        self.resize(1320, 820)
        self.setMinimumSize(1060, 680)
        set_window_icon(self, "icon_backend.ico")

        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        layout.addWidget(self._build_sidebar())
        self.stack = QStackedWidget()
        layout.addWidget(self.stack, 1)

        self.dashboard_page = self._page_dashboard()
        self.rules_page = self._page_rules()
        self.waybill_parse_page = self._page_waybill_parse()
        self.stalls_page = self._page_stalls()
        self.templates_page = self._page_templates()
        self.images_page = self._page_images()
        self.settings_page = self._page_settings()
        for page in [
            self.dashboard_page,
            self.rules_page,
            self.waybill_parse_page,
            self.stalls_page,
            self.templates_page,
            self.images_page,
            self.settings_page,
        ]:
            self.stack.addWidget(page)

        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.reload_data()
        self.statusBar().showMessage("就绪")

    def _build_sidebar(self):
        side = QFrame()
        side.setObjectName("Sidebar")
        side.setFixedWidth(198)
        layout = QVBoxLayout(side)
        layout.setContentsMargins(0, 0, 0, 12)
        layout.setSpacing(10)

        brand = QFrame()
        brand.setObjectName("BrandBlock")
        brand_layout = QVBoxLayout(brand)
        brand_layout.setContentsMargins(16, 16, 16, 14)
        brand_layout.setSpacing(4)
        title = QLabel(APP_NAME)
        title.setObjectName("AppTitle")
        title.setWordWrap(True)
        brand_layout.addWidget(title)
        subtitle = QLabel(f"{APP_VERSION} {APP_EDITION}")
        subtitle.setObjectName("Muted")
        brand_layout.addWidget(subtitle)
        layout.addWidget(brand)

        self.nav = QListWidget()
        for name in ["数据看板", "鞋款分类", "面单解析", "鞋款档口", "导入模板", "图片关系", "系统设置"]:
            QListWidgetItem(name, self.nav)
        layout.addWidget(self.nav, 1)

        self.version_label = QLabel(f"版本：{display_version()}")
        self.version_label.setObjectName("Muted")
        layout.addWidget(self.version_label)
        return side

    def _content_layout(self, title, subtitle=""):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.setContentsMargins(16, 14, 18, 12)
        layout.setSpacing(10)
        layout.addWidget(page_header(title, subtitle))
        return page, layout

    def _editor_context(self, title, description, state_title, state_detail):
        frame = QFrame()
        frame.setObjectName("EditorHint")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        title_label = QLabel(title)
        title_label.setObjectName("EditorTitle")
        description_label = QLabel(description)
        description_label.setObjectName("Muted")
        description_label.setWordWrap(True)
        state_label = QLabel(state_title)
        state_label.setObjectName("EditorState")
        detail_label = QLabel(state_detail)
        detail_label.setObjectName("Muted")
        detail_label.setWordWrap(True)

        layout.addWidget(title_label)
        layout.addWidget(description_label)
        layout.addSpacing(6)
        layout.addWidget(state_label)
        layout.addWidget(detail_label)
        return frame, state_label, detail_label

    def _form_card(self):
        frame = QFrame()
        frame.setObjectName("EditorForm")
        frame.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        form = QFormLayout(frame)
        form.setContentsMargins(14, 12, 14, 12)
        form.setSpacing(9)
        form.setFormAlignment(Qt.AlignTop)
        form.setLabelAlignment(Qt.AlignRight | Qt.AlignVCenter)
        return frame, form

    def _page_dashboard(self):
        page, layout = self._content_layout("数据看板", "读取当前共享数据目录，快速查看模板、鞋款关系和输出位置。")

        self.metric_cards = {}
        grid = QGridLayout()
        names = [
            ("templates", "导入模板"),
            ("rules", "鞋款分类"),
            ("stalls", "鞋款档口"),
            ("images", "图片绑定"),
        ]
        for col, (key, title) in enumerate(names):
            frame, value, sub = card(title, "0", "")
            self.metric_cards[key] = (value, sub)
            grid.addWidget(frame, 0, col)
        layout.addLayout(grid)

        splitter = QSplitter(Qt.Horizontal)
        self.preview_box = QTextEdit()
        self.preview_box.setReadOnly(True)
        splitter.addWidget(titled_panel("鞋款规则预览", self.preview_box))

        self.path_box = QTextEdit()
        self.path_box.setReadOnly(True)
        splitter.addWidget(titled_panel("数据位置", self.path_box))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        refresh = make_button("刷新数据", primary=True)
        open_data = make_button("打开数据目录")
        open_output = make_button("打开输出目录")
        backup = make_button("备份主数据")
        refresh.clicked.connect(self.reload_data)
        open_data.clicked.connect(lambda: open_path(get_data_dir()))
        open_output.clicked.connect(lambda: open_path(get_output_dir()))
        backup.clicked.connect(self.backup_data)
        for btn in [refresh, open_data, open_output, backup]:
            buttons.addWidget(btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def _page_rules(self):
        page, layout = self._content_layout("传统鞋款分类规则", "传统导入模式先把不同模板统一成五字段，再按规则归入鞋款。")
        splitter = QSplitter(Qt.Horizontal)

        self.rule_table = QTableWidget()
        configure_table(self.rule_table, ["鞋款分类", "识别鞋款", "关键词", "匹配字段", "规格清洗词"])
        self.rule_table.itemSelectionChanged.connect(self.load_selected_rule)
        splitter.addWidget(titled_panel("鞋款分类列表", self.rule_table))

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        hint, self.rule_state_title, self.rule_state_detail = self._editor_context(
            "鞋款识别配置",
            "规则主要匹配五字段里的“鞋款”。规格、尺码、数量和备注保持原样供后续发货判断。",
            "准备新增鞋款分类",
            "从左侧选择一条规则可修改；直接填写鞋款分类和关键词可新增。",
        )
        editor_layout.addWidget(hint)

        form_widget, form = self._form_card()
        self.rule_category = QLineEdit()
        self.rule_category.setPlaceholderText("例如：vapor / 昂跑 / 5.0")
        self.rule_output_shoe = QLineEdit()
        self.rule_output_shoe.setPlaceholderText("例如：AC / 175 / 4.0；留空则按关键词自动推断")
        self.rule_keyword = QLineEdit()
        self.rule_keyword.setPlaceholderText("例如：vapor / Cloudtilt / 5.0")
        self.rule_field = QComboBox()
        self.rule_field.addItems(["鞋款", "规格", "备注", "尺码", "数量", "全部五字段", "原始打印信息"])
        self.rule_remove = QLineEdit()
        self.rule_remove.setPlaceholderText("命中后需要从规格里清掉的词，可留空")
        form.addRow("鞋款分类", self.rule_category)
        form.addRow("识别鞋款", self.rule_output_shoe)
        form.addRow("关键词", self.rule_keyword)
        form.addRow("匹配字段", self.rule_field)
        form.addRow("规格清洗词", self.rule_remove)
        btns = QHBoxLayout()
        add_btn = make_button("新增/更新", primary=True)
        del_btn = make_button("删除", danger=True)
        clear_btn = make_button("清空输入")
        add_btn.clicked.connect(self.save_rule)
        del_btn.clicked.connect(self.delete_rule)
        clear_btn.clicked.connect(self.clear_rule_form)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addWidget(clear_btn)
        form.addRow(btns)
        editor_layout.addWidget(form_widget)
        editor_layout.addStretch(1)
        splitter.addWidget(titled_panel("鞋款规则配置", editor))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _page_waybill_parse(self):
        page, layout = self._content_layout("面单解析", "打开采集到的原始 Excel，先识别成五字段；这里的商品简称会作为面单线的鞋款。")

        toolbar = QHBoxLayout()
        open_btn = make_button("打开面单Excel", primary=True)
        reparse_btn = make_button("重新识别")
        fill_blank_btn = make_button("补识别空白")
        save_result_btn = make_button("保存修改", primary=True)
        export_btn = make_button("另存识别Excel")
        output_btn = make_button("打开输出目录")
        open_btn.clicked.connect(self.open_waybill_parse_excel)
        reparse_btn.clicked.connect(self.reparse_waybill_source)
        fill_blank_btn.clicked.connect(self.fill_blank_waybill_shoes)
        save_result_btn.clicked.connect(self.save_waybill_parse_edits)
        export_btn.clicked.connect(self.export_waybill_parse_excel)
        output_btn.clicked.connect(lambda: open_path(get_output_dir()))
        self.waybill_parse_file_label = QLabel("未选择原始Excel")
        self.waybill_parse_file_label.setObjectName("Muted")
        toolbar.addWidget(open_btn)
        toolbar.addWidget(reparse_btn)
        toolbar.addWidget(fill_blank_btn)
        toolbar.addWidget(save_result_btn)
        toolbar.addWidget(export_btn)
        toolbar.addWidget(output_btn)
        toolbar.addWidget(self.waybill_parse_file_label, 1)
        layout.addLayout(toolbar)

        filter_bar = QHBoxLayout()
        filter_bar.addWidget(QLabel("图片识别"))
        self.waybill_image_filter = QComboBox()
        self.waybill_image_filter.addItems(["全部", "未识别", "已识别"])
        self.waybill_image_filter.currentTextChanged.connect(self.apply_waybill_parse_filter)
        filter_bar.addWidget(self.waybill_image_filter)
        filter_bar.addWidget(QLabel("关键词"))
        self.waybill_text_filter = QLineEdit()
        self.waybill_text_filter.setPlaceholderText("筛选店铺、商品、规格、尺码、原文")
        self.waybill_text_filter.textChanged.connect(self.apply_waybill_parse_filter)
        filter_bar.addWidget(self.waybill_text_filter, 1)
        clear_filter_btn = make_button("清空筛选")
        clear_filter_btn.clicked.connect(self.clear_waybill_parse_filter)
        filter_bar.addWidget(clear_filter_btn)
        layout.addLayout(filter_bar)

        splitter = QSplitter(Qt.Horizontal)
        self.waybill_parse_table = QTableWidget()
        configure_table(self.waybill_parse_table, RAW_PIPELINE_INTERNAL_FIELDS)
        self.waybill_parse_table.setSelectionMode(QTableWidget.ExtendedSelection)
        self.waybill_parse_table.setSortingEnabled(True)
        splitter.addWidget(titled_panel("识别结果（可直接修改）", self.waybill_parse_table))

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        hint, self.waybill_rule_state_title, self.waybill_rule_state_detail = self._editor_context(
            "面单原文识别规则",
            "规则只负责把打印信息原文识别为鞋款和规格；识别后仍可在左侧表格直接手动修正。",
            "准备新增解析规则",
            "规格关键词、店铺关键词、标题关键词都在这里维护；标题关键词会匹配完整打印标题。",
        )
        editor_layout.addWidget(hint)

        self.waybill_rule_table = QTableWidget()
        configure_table(self.waybill_rule_table, ["规则类型", "商品简称", "关键词", "清洗词"])
        self.waybill_rule_table.itemSelectionChanged.connect(self.load_selected_waybill_rule)
        editor_layout.addWidget(self.waybill_rule_table, 1)

        form_widget, form = self._form_card()
        self.waybill_rule_type = QComboBox()
        self.waybill_rule_type.addItems(["规格关键词", "店铺关键词", "标题关键词"])
        self.waybill_rule_shoe = QLineEdit()
        self.waybill_rule_shoe.setPlaceholderText("例如：昂跑 / ACG / 科比6代 / 5.0")
        self.waybill_rule_keywords = QLineEdit()
        self.waybill_rule_keywords.setPlaceholderText("多个关键词用 / 或逗号分隔，例如：登山鞋 / A5J / Cloudtilt")
        self.waybill_rule_prefixes = QLineEdit()
        self.waybill_rule_prefixes.setPlaceholderText("识别后要从输出规格开头清掉的词，可留空")
        form.addRow("规则类型", self.waybill_rule_type)
        form.addRow("商品简称", self.waybill_rule_shoe)
        form.addRow("关键词", self.waybill_rule_keywords)
        form.addRow("清洗词", self.waybill_rule_prefixes)
        btns = QHBoxLayout()
        save_btn = make_button("新增/更新", primary=True)
        del_btn = make_button("删除", danger=True)
        clear_btn = make_button("清空输入")
        apply_btn = make_button("保存并重新识别")
        save_btn.clicked.connect(self.save_waybill_rule)
        del_btn.clicked.connect(self.delete_waybill_rule)
        clear_btn.clicked.connect(self.clear_waybill_rule_form)
        apply_btn.clicked.connect(self.save_waybill_rule_and_reparse)
        btns.addWidget(save_btn)
        btns.addWidget(del_btn)
        btns.addWidget(clear_btn)
        btns.addWidget(apply_btn)
        form.addRow(btns)
        editor_layout.addWidget(form_widget)
        splitter.addWidget(titled_panel("解析规则", editor))
        splitter.setStretchFactor(0, 4)
        splitter.setStretchFactor(1, 2)
        layout.addWidget(splitter, 1)
        return page

    def _page_stalls(self):
        page, layout = self._content_layout("鞋款档口", "维护鞋款对应的档口；鞋款会合并读取传统鞋款分类和面单解析规则。")
        splitter = QSplitter(Qt.Horizontal)

        self.stall_table = QTableWidget()
        configure_table(self.stall_table, ["鞋款", "鞋款档口"])
        self.stall_table.itemSelectionChanged.connect(self.load_selected_stall)
        splitter.addWidget(titled_panel("鞋款档口列表", self.stall_table))

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        hint, self.stall_state_title, self.stall_state_detail = self._editor_context(
            "鞋款档口配置",
            "同一个鞋款只对应一个档口。修改后会影响后续订单输出的 Sheet 或分文档结果。",
            "准备新增鞋款档口",
            "从左侧选择鞋款可修改；直接填写鞋款和档口可新增。",
        )
        editor_layout.addWidget(hint)

        form_widget, form = self._form_card()
        self.stall_category = QLineEdit()
        self.stall_category.setPlaceholderText("例如：ACG / 昂跑 / 5.0")
        self.stall_value = QLineEdit()
        self.stall_value.setPlaceholderText("例如：1199 / 默认 / A档")
        form.addRow("鞋款", self.stall_category)
        form.addRow("鞋款档口", self.stall_value)
        btns = QHBoxLayout()
        add_btn = make_button("新增/更新", primary=True)
        del_btn = make_button("删除", danger=True)
        clear_btn = make_button("清空输入")
        add_btn.clicked.connect(self.save_stall)
        del_btn.clicked.connect(self.delete_stall)
        clear_btn.clicked.connect(self.clear_stall_form)
        btns.addWidget(add_btn)
        btns.addWidget(del_btn)
        btns.addWidget(clear_btn)
        form.addRow(btns)
        editor_layout.addWidget(form_widget)
        editor_layout.addStretch(1)
        splitter.addWidget(titled_panel("鞋款档口配置", editor))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _page_templates(self):
        page, layout = self._content_layout("导入模板", "维护不同来源订单 Excel 的字段映射，保证导入时读取正确列。")
        splitter = QSplitter(Qt.Horizontal)

        self.template_table = QTableWidget()
        configure_table(self.template_table, ["模板名", "模式", "鞋款字段", "规格字段", "尺码字段", "数量字段", "备注字段"])
        self.template_table.itemSelectionChanged.connect(self.load_selected_template)
        splitter.addWidget(titled_panel("模板列表", self.template_table))

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        hint, self.template_state_title, self.template_state_detail = self._editor_context(
            "Excel字段映射",
            "表头模式使用列名读取，列号模式使用 Excel 字母列；面单原文模式只读取打印信息。",
            "准备新增模板",
            "从左侧选择模板可修改；新增模板建议先复制已有模板字段再微调。",
        )
        editor_layout.addWidget(hint)

        form_widget, form = self._form_card()
        self.tpl_name = QLineEdit()
        self.tpl_name.setPlaceholderText("例如：1688新版-表头模式")
        self.tpl_mode = QComboBox()
        self.tpl_mode.addItems(["表头", "列号", RAW_WAYBILL_MODE])
        self.tpl_short_name = QLineEdit()
        self.tpl_short_name.setPlaceholderText("表头模式：鞋款/商品简称")
        self.tpl_spec = QLineEdit()
        self.tpl_spec.setPlaceholderText("表头模式：销售规格/鞋款")
        self.tpl_size = QLineEdit()
        self.tpl_size.setPlaceholderText("表头模式：尺码字段，可留空")
        self.tpl_qty = QLineEdit()
        self.tpl_qty.setPlaceholderText("表头模式：商品数量")
        self.tpl_remark = QLineEdit()
        self.tpl_remark.setPlaceholderText("表头模式：备注，可留空")
        self.tpl_title_col = QLineEdit()
        self.tpl_title_col.setPlaceholderText("列号模式：如 S")
        self.tpl_qty_col = QLineEdit()
        self.tpl_qty_col.setPlaceholderText("列号模式：如 V")
        self.tpl_item_sep = QLineEdit()
        self.tpl_item_sep.setPlaceholderText("默认 ;")
        self.tpl_spec_split = QLineEdit()
        self.tpl_spec_split.setPlaceholderText("默认 ，")
        for label, widget in [
            ("模板名", self.tpl_name),
            ("模式", self.tpl_mode),
            ("鞋款字段", self.tpl_short_name),
            ("规格字段", self.tpl_spec),
            ("尺码字段", self.tpl_size),
            ("数量字段", self.tpl_qty),
            ("备注字段", self.tpl_remark),
            ("标题列号", self.tpl_title_col),
            ("数量列号", self.tpl_qty_col),
            ("多商品分隔", self.tpl_item_sep),
            ("规格分隔", self.tpl_spec_split),
        ]:
            form.addRow(label, widget)
        btns = QHBoxLayout()
        detect_btn = make_button("识别Excel表头")
        save_btn = make_button("新增/更新", primary=True)
        del_btn = make_button("删除", danger=True)
        clear_btn = make_button("清空输入")
        detect_btn.clicked.connect(self.detect_template_from_excel)
        save_btn.clicked.connect(self.save_template)
        del_btn.clicked.connect(self.delete_template)
        clear_btn.clicked.connect(self.clear_template_form)
        btns.addWidget(detect_btn)
        btns.addWidget(save_btn)
        btns.addWidget(del_btn)
        btns.addWidget(clear_btn)
        form.addRow(btns)
        editor_layout.addWidget(form_widget)
        editor_layout.addStretch(1)
        splitter.addWidget(titled_panel("模板配置", editor))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _page_images(self):
        page, layout = self._content_layout("图片关系", "维护鞋款、规格、别名与图片文件的绑定，用于生成订单时自动插图。")

        filter_bar = QHBoxLayout()
        self.image_category_filter = QComboBox()
        self.image_keyword = QLineEdit()
        self.image_keyword.setPlaceholderText("关键词搜索")
        search = make_button("搜索", primary=True)
        search.clicked.connect(self.render_images)
        filter_bar.addWidget(QLabel("鞋款"))
        filter_bar.addWidget(self.image_category_filter)
        filter_bar.addWidget(QLabel("关键词"))
        filter_bar.addWidget(self.image_keyword, 1)
        filter_bar.addWidget(search)
        layout.addLayout(filter_bar)

        bulk_bar = QHBoxLayout()
        for text, action, primary in [
            ("生成SKU图片模板", self.create_sku_image_template, False),
            ("预览批量导入", lambda: self.run_sku_image_import(dry_run=True), False),
            ("批量导入图片", lambda: self.run_sku_image_import(dry_run=False), True),
            ("生成缺图清单", self.create_missing_image_report, False),
        ]:
            btn = make_button(text, primary=primary)
            btn.clicked.connect(action)
            bulk_bar.addWidget(btn)
        bulk_bar.addStretch(1)
        layout.addLayout(bulk_bar)

        splitter = QSplitter(Qt.Horizontal)
        self.image_table = QTableWidget()
        configure_table(self.image_table, ["鞋款", "规格", "别名", "图片文件"])
        self.image_table.itemSelectionChanged.connect(self.load_selected_image)
        splitter.addWidget(titled_panel("图片绑定列表", self.image_table))

        editor = QWidget()
        editor_layout = QVBoxLayout(editor)
        editor_layout.setContentsMargins(0, 0, 0, 0)
        editor_layout.setSpacing(10)
        hint, self.image_state_title, self.image_state_detail = self._editor_context(
            "图片绑定配置",
            "规格可以绑定一张主图，别名用于处理订单里不同写法，例如“C6全黑”和“Cloud6 黑”。",
            "准备新增图片绑定",
            "从左侧选择记录可预览和替换图片；也可以拖入图片后保存为新绑定。",
        )
        editor_layout.addWidget(hint)

        form_widget = QWidget()
        edit_layout = QVBoxLayout(form_widget)
        edit_layout.setContentsMargins(0, 0, 0, 0)
        edit_layout.setSpacing(10)
        self.image_preview = ImageDropPreview()
        self.image_preview.fileSelected.connect(self.set_image_file)
        edit_layout.addWidget(self.image_preview)

        form_area, form = self._form_card()
        self.img_category = QLineEdit()
        self.img_category.setPlaceholderText("例如：acg")
        self.img_spec = QLineEdit()
        self.img_spec.setPlaceholderText("例如：卡其高帮")
        self.img_aliases = QLineEdit()
        self.img_aliases.setPlaceholderText("多个别名用逗号、分号或顿号分隔")
        self.img_path = QLineEdit()
        self.img_path.setReadOnly(True)
        choose = make_button("选择图片")
        choose.clicked.connect(self.choose_image)
        path_line = QHBoxLayout()
        path_line.addWidget(self.img_path, 1)
        path_line.addWidget(choose)
        form.addRow("鞋款", self.img_category)
        form.addRow("规格", self.img_spec)
        form.addRow("别名", self.img_aliases)
        form.addRow("图片", path_line)
        btns = QHBoxLayout()
        save_btn = make_button("新增/更新", primary=True)
        del_btn = make_button("删除", danger=True)
        clear_btn = make_button("清空输入")
        save_btn.clicked.connect(self.save_image)
        del_btn.clicked.connect(self.delete_image)
        clear_btn.clicked.connect(self.clear_image_form)
        btns.addWidget(save_btn)
        btns.addWidget(del_btn)
        btns.addWidget(clear_btn)
        form.addRow(btns)
        edit_layout.addWidget(form_area)
        editor_layout.addWidget(form_widget)
        editor_layout.addStretch(1)
        splitter.addWidget(titled_panel("图片配置", editor))
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)
        layout.addWidget(splitter, 1)
        return page

    def _page_settings(self):
        page, layout = self._content_layout("系统设置", "路径、备份和当前版本信息。")
        self.settings_box = QTextEdit()
        self.settings_box.setReadOnly(True)
        layout.addWidget(titled_panel("系统信息", self.settings_box), 1)

        buttons = QHBoxLayout()
        for text, action in [
            ("打开数据目录", lambda: open_path(get_data_dir())),
            ("打开图片目录", lambda: open_path(get_images_dir())),
            ("打开图片索引", lambda: open_path(get_image_category_dir())),
            ("打开输出目录", lambda: open_path(get_output_dir())),
            ("备份主数据", self.backup_data),
        ]:
            btn = make_button(text, primary=text == "备份主数据")
            btn.clicked.connect(action)
            buttons.addWidget(btn)
        buttons.addStretch(1)
        layout.addLayout(buttons)
        return page

    def reload_data(self):
        try:
            self.data = load_data(auto_save_on_read=False)
            self.system, self.system_id = get_active_system(self.data)
            self.render_dashboard()
            self.render_rules()
            self.render_waybill_parse_rules()
            self.render_stalls()
            self.render_templates()
            self.refresh_image_categories()
            self.render_images()
            self.render_settings()
            self.statusBar().showMessage(f"数据已刷新：{datetime.now().strftime('%H:%M:%S')}")
        except Exception as exc:
            show_error(self, "读取数据失败", exc)

    def persist(self):
        self.data["systems"][self.system_id] = self.system
        self.data["active_system"] = self.system_id
        self.data["category_rules"] = self.system.get("category_rules", [])
        self.data["waybill_parse_rules"] = self.system.get("waybill_parse_rules", {})
        self.data["stall_map"] = self.system.get("stall_map", {})
        self.data["image_map"] = {}
        self.data["import_templates"] = self.system.get("import_templates", [])
        self.data["active_template"] = self.system.get("active_template", "")
        save_data(self.data)
        save_templates_fast(self.system.get("import_templates", []))
        self.statusBar().showMessage("数据已保存")
        self.render_dashboard()
        self.render_settings()

    def render_dashboard(self):
        summary = preview_data_summary(self.data, count_image_entries=False)
        values = {
            "templates": (summary["templates_count"], "导入模板"),
            "rules": (summary["rules_count"], "鞋款分类规则"),
            "stalls": (summary["stalls_count"], "鞋款档口关系"),
            "images": (summary["images_count"], f"分片 {summary['image_category_files']} 个 / {summary['image_storage_mb']} MB"),
        }
        for key, (value, sub) in values.items():
            self.metric_cards[key][0].setText(str(value))
            self.metric_cards[key][1].setText(sub)
        self.preview_box.setPlainText(
            "模板：\n"
            + "\n".join(f"  - {x}" for x in summary["templates_preview"])
            + "\n\n鞋款分类规则：\n"
            + "\n".join(f"  - {x}" for x in summary["rules_preview"])
            + "\n\n图片鞋款分类：\n"
            + "\n".join(f"  - {x}" for x in summary["images_preview"])
        )
        self.path_box.setPlainText(
            f"当前系统：{summary['system_name']} ({summary['system_id']})\n"
            f"主数据文件：{get_data_file()}\n"
            f"数据目录：{get_data_dir()}\n"
            f"图片目录：{get_images_dir()}\n"
            f"输出目录：{get_output_dir()}"
        )

    def render_rules(self):
        rules = self.system.get("category_rules", [])
        self.rule_table.setRowCount(0)
        for row, rule in enumerate(rules):
            set_table_row(
                self.rule_table,
                row,
                [
                    rule.get("category", ""),
                    rule.get("output_shoe", "") or rule.get("shoe_name", ""),
                    rule.get("keyword", ""),
                    "鞋款" if rule.get("field", "") in {"商品简称", "鞋款简称"} else rule.get("field", ""),
                    rule.get("remove_words", ""),
                ],
            )

    def load_selected_rule(self):
        row = selected_row(self.rule_table)
        if row < 0:
            return
        rules = self.system.get("category_rules", [])
        if row >= len(rules):
            return
        rule = rules[row]
        self.rule_category.setText(rule.get("category", ""))
        self.rule_output_shoe.setText(rule.get("output_shoe", "") or rule.get("shoe_name", ""))
        self.rule_keyword.setText(rule.get("keyword", ""))
        self.rule_remove.setText(rule.get("remove_words", ""))
        field_text = rule.get("field", "鞋款")
        if field_text in {"商品简称", "鞋款简称"}:
            field_text = "鞋款"
        elif field_text == "销售规格":
            field_text = "规格"
        elif field_text in {"全部", "货品标题"}:
            field_text = "全部五字段"
        idx = self.rule_field.findText(field_text)
        self.rule_field.setCurrentIndex(max(idx, 0))
        self.rule_state_title.setText(f"正在编辑：{rule.get('category', '')}")
        self.rule_state_detail.setText(
            f"识别鞋款：{rule.get('output_shoe', '') or rule.get('shoe_name', '') or '自动'}    关键词：{rule.get('keyword', '')}    匹配字段：{field_text}    规格清洗：{rule.get('remove_words', '') or '无'}"
        )

    def save_rule(self):
        category = self.rule_category.text().strip()
        keyword = self.rule_keyword.text().strip()
        if not category or not keyword:
            show_info(self, "缺少内容", "鞋款分类和关键词不能为空。")
            return
        row = selected_row(self.rule_table)
        rule = {
            "category": category,
            "output_shoe": self.rule_output_shoe.text().strip(),
            "keyword": keyword,
            "field": self.rule_field.currentText(),
            "remove_words": self.rule_remove.text().strip(),
        }
        rules = self.system.setdefault("category_rules", [])
        if row >= 0 and row < len(rules):
            rules[row] = rule
        else:
            rules.append(rule)
        self.persist()
        self.render_rules()
        self.refresh_shared_shoe_views()
        self.rule_state_title.setText(f"已保存：{category}")
        self.rule_state_detail.setText(f"识别鞋款：{rule['output_shoe'] or '自动'}    关键词：{keyword}    匹配字段：{rule['field']}    规格清洗：{rule['remove_words'] or '无'}")

    def delete_rule(self):
        row = selected_row(self.rule_table)
        rules = self.system.setdefault("category_rules", [])
        if row >= 0 and row < len(rules):
            rules.pop(row)
            self.persist()
            self.render_rules()
            self.refresh_shared_shoe_views()
            self.clear_rule_form()

    def clear_rule_form(self):
        self.rule_category.clear()
        self.rule_output_shoe.clear()
        self.rule_keyword.clear()
        self.rule_remove.clear()
        self.rule_field.setCurrentIndex(0)
        self.rule_table.clearSelection()
        self.rule_state_title.setText("准备新增鞋款分类")
        self.rule_state_detail.setText("从左侧选择一条规则可修改；直接填写鞋款分类和关键词可新增。")

    def waybill_rule_meta(self, label):
        mapping = {
            "规格关键词": ("spec_keyword_rules", "strip_prefixes"),
            "店铺关键词": ("shop_keyword_rules", "strip_prefixes"),
            "标题关键词": ("title_shoe_rules", "spec_prefixes"),
        }
        return mapping.get(label, mapping["规格关键词"])

    def waybill_rule_label(self, key):
        mapping = {
            "spec_keyword_rules": "规格关键词",
            "shop_keyword_rules": "店铺关键词",
            "title_shoe_rules": "标题关键词",
        }
        return mapping.get(key, "规格关键词")

    def split_waybill_rule_input(self, text):
        result = []
        for part in str(text or "").replace("\n", "/").split("/"):
            for item in part.replace("，", ",").replace("、", ",").replace("；", ",").replace(";", ",").split(","):
                item = item.strip()
                if item and item not in result:
                    result.append(item)
        return result

    def upsert_learned_waybill_rule(self, config, key, shoe, keyword, prefixes=None):
        shoe = str(shoe or "").strip()
        keyword = str(keyword or "").strip()
        if not shoe or not keyword or shoe in {"未知", "未分类"}:
            return 0

        prefix_key = "spec_prefixes" if key == "title_shoe_rules" else "strip_prefixes"
        rules = config.setdefault(key, [])
        target = None
        for rule in rules:
            if str(rule.get("shoe") or "").strip() == shoe:
                target = rule
                break
        if target is None:
            target = {"shoe": shoe, "keywords": []}
            rules.append(target)

        changed = 0
        keywords = list(target.get("keywords") or [])
        if keyword not in keywords:
            keywords.append(keyword)
            target["keywords"] = keywords
            changed += 1

        if prefixes:
            old_prefixes = list(target.get(prefix_key) or [])
            for prefix in prefixes:
                prefix = str(prefix or "").strip()
                if prefix and prefix not in old_prefixes:
                    old_prefixes.append(prefix)
            if old_prefixes:
                target[prefix_key] = old_prefixes
        return changed

    def learned_shop_keywords_from_row(self, row):
        text = str(row.get("店铺关键词", "") or "").strip()
        result = []
        for item in self.split_waybill_rule_input(text):
            product_codes = re.findall(r"(?:科|乔)\d+", item)
            if len(product_codes) >= 2:
                continue
            if item and " " not in item and len(item) <= 24 and item not in result:
                result.append(item)

        compact = text.replace(" ", "")
        for pattern in (
            r"带木one帆布kw",
            r"one帆布kw",
            r"vap\d*",
            r"of\d*",
            r"sa3\.0",
            r"阿尔",
        ):
            for match in re.findall(pattern, compact, flags=re.I):
                if match and match not in result:
                    result.append(match)
        if "带木one帆布kw" in result and "one帆布kw" not in result:
            result.append("one帆布kw")
        return result

    def learned_spec_keywords_from_row(self, row):
        spec = str(row.get("规格", "") or "").strip()
        if not spec:
            return []

        result = []
        for pattern in (
            r"Cloudtilt",
            r"Cloud",
            r"科\d+",
            r"乔\d+(?:代)?",
            r"\d+代",
            r"\d+\.\d+",
            r"vap\d*",
            r"of\d*",
            r"sa3\.0",
        ):
            for match in re.findall(pattern, spec, flags=re.I):
                match = str(match or "").strip()
                if not match:
                    continue
                prefixes = []
                if spec.casefold().startswith(match.casefold()) and not match.casefold().startswith("cloud"):
                    prefixes.append(match)
                item = (match, prefixes)
                if item not in result:
                    result.append(item)
        return result

    def learn_waybill_rules_from_rows(self, rows):
        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        changed = 0
        for row in rows:
            shoe = str(row.get("商品简称", "") or "").strip()
            if not shoe:
                continue
            for keyword in self.learned_shop_keywords_from_row(row):
                changed += self.upsert_learned_waybill_rule(config, "shop_keyword_rules", shoe, keyword)
            for keyword, prefixes in self.learned_spec_keywords_from_row(row):
                changed += self.upsert_learned_waybill_rule(config, "spec_keyword_rules", shoe, keyword, prefixes)

        if changed:
            self.system["waybill_parse_rules"] = normalize_rule_config(config)
            self.persist()
            self.render_waybill_parse_rules()
            self.refresh_shared_shoe_views()
        return changed

    def waybill_rule_shoe_names(self):
        names = []
        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        for key in ["spec_keyword_rules", "shop_keyword_rules", "title_shoe_rules"]:
            for rule in config.get(key, []):
                shoe = str(rule.get("shoe", "") or "").strip()
                if shoe and shoe not in names:
                    names.append(shoe)
        return names

    def known_shoe_names(self):
        names = []
        seen = set()

        def add(value):
            value = str(value or "").strip()
            marker = normalize_text(value).casefold()
            if value and marker not in seen:
                seen.add(marker)
                names.append(value)

        for shoe in self.waybill_rule_shoe_names():
            add(shoe)
        for rule in self.system.get("category_rules", []) or []:
            add(rule.get("category", ""))
        for shoe in (self.system.get("stall_map", {}) or {}).keys():
            add(shoe)
        for shoe in list_image_category_names():
            add(shoe)
        return sorted(names, key=lambda item: item.casefold())

    def refresh_shared_shoe_views(self):
        if hasattr(self, "stall_table"):
            self.render_stalls()
        if hasattr(self, "image_category_filter"):
            self.refresh_image_categories()

    def render_waybill_parse_rules(self):
        if not hasattr(self, "waybill_rule_table"):
            return
        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        self.system["waybill_parse_rules"] = config
        self.waybill_parse_rule_index = []
        self.waybill_rule_table.setRowCount(0)
        for key in ["spec_keyword_rules", "shop_keyword_rules", "title_shoe_rules"]:
            prefix_key = "spec_prefixes" if key == "title_shoe_rules" else "strip_prefixes"
            for index, rule in enumerate(config.get(key, [])):
                self.waybill_parse_rule_index.append((key, index))
                set_table_row(
                    self.waybill_rule_table,
                    len(self.waybill_parse_rule_index) - 1,
                    [
                        self.waybill_rule_label(key),
                        rule.get("shoe", ""),
                        " / ".join(rule.get("keywords", [])),
                        " / ".join(rule.get(prefix_key, [])),
                    ],
                )

    def load_selected_waybill_rule(self):
        row = selected_row(self.waybill_rule_table)
        if row < 0 or row >= len(self.waybill_parse_rule_index):
            return
        key, index = self.waybill_parse_rule_index[row]
        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        rules = config.get(key, [])
        if index >= len(rules):
            return
        rule = rules[index]
        label = self.waybill_rule_label(key)
        prefix_key = "spec_prefixes" if key == "title_shoe_rules" else "strip_prefixes"
        self.waybill_rule_type.setCurrentText(label)
        self.waybill_rule_shoe.setText(rule.get("shoe", ""))
        self.waybill_rule_keywords.setText(" / ".join(rule.get("keywords", [])))
        self.waybill_rule_prefixes.setText(" / ".join(rule.get(prefix_key, [])))
        self.waybill_rule_state_title.setText(f"正在编辑：{label} / {rule.get('shoe', '')}")
        self.waybill_rule_state_detail.setText(f"关键词：{' / '.join(rule.get('keywords', []))}")

    def save_waybill_rule(self):
        label = self.waybill_rule_type.currentText()
        key, prefix_key = self.waybill_rule_meta(label)
        shoe = self.waybill_rule_shoe.text().strip()
        keywords = self.split_waybill_rule_input(self.waybill_rule_keywords.text())
        prefixes = self.split_waybill_rule_input(self.waybill_rule_prefixes.text())
        if not shoe or not keywords:
            show_info(self, "缺少内容", "商品简称和关键词不能为空。")
            return False

        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        rule = {"shoe": shoe, "keywords": keywords}
        if prefixes:
            rule[prefix_key] = prefixes

        row = selected_row(self.waybill_rule_table)
        if row >= 0 and row < len(self.waybill_parse_rule_index):
            old_key, old_index = self.waybill_parse_rule_index[row]
            if old_key == key and old_index < len(config.get(key, [])):
                config[key][old_index] = rule
            else:
                if old_index < len(config.get(old_key, [])):
                    config[old_key].pop(old_index)
                config.setdefault(key, []).append(rule)
        else:
            config.setdefault(key, []).append(rule)

        self.system["waybill_parse_rules"] = normalize_rule_config(config)
        self.persist()
        self.render_waybill_parse_rules()
        self.refresh_shared_shoe_views()
        self.waybill_rule_state_title.setText(f"已保存：{label} / {shoe}")
        self.waybill_rule_state_detail.setText(f"关键词：{' / '.join(keywords)}")
        return True

    def save_waybill_rule_and_reparse(self):
        if self.save_waybill_rule():
            if self.waybill_parse_source_file:
                self.reparse_waybill_source()
            else:
                self.fill_blank_waybill_shoes()

    def delete_waybill_rule(self):
        row = selected_row(self.waybill_rule_table)
        if row < 0 or row >= len(self.waybill_parse_rule_index):
            return
        key, index = self.waybill_parse_rule_index[row]
        config = normalize_rule_config(self.system.get("waybill_parse_rules", {}))
        if index < len(config.get(key, [])):
            config[key].pop(index)
            self.system["waybill_parse_rules"] = config
            self.persist()
            self.render_waybill_parse_rules()
            self.refresh_shared_shoe_views()
            self.clear_waybill_rule_form()

    def clear_waybill_rule_form(self):
        self.waybill_rule_type.setCurrentIndex(0)
        self.waybill_rule_shoe.clear()
        self.waybill_rule_keywords.clear()
        self.waybill_rule_prefixes.clear()
        self.waybill_rule_table.clearSelection()
        self.waybill_rule_state_title.setText("准备新增解析规则")
        self.waybill_rule_state_detail.setText("规格关键词、店铺关键词、标题关键词都在这里维护；标题关键词会匹配完整打印标题。")

    def update_waybill_image_status(self, rows):
        categories = sorted({
            normalize_text(row.get("商品简称", ""))
            for row in rows
            if normalize_text(row.get("商品简称", ""))
        })
        matcher = ImageMatcher(load_image_map_for_categories(self.system, categories))
        for row in rows:
            shoe = normalize_text(row.get("商品简称", ""))
            spec = normalize_text(row.get("规格", ""))
            if not shoe or not spec:
                row[WAYBILL_IMAGE_STATUS_FIELD] = "未识别"
                continue
            item = matcher.find(
                shoe,
                spec,
                row.get("原始打印信息", ""),
                row.get("店铺关键词", ""),
                row.get("面单模式", ""),
            )
            row[WAYBILL_IMAGE_STATUS_FIELD] = "已识别" if item else "未识别"
        return rows

    def clear_waybill_parse_filter(self):
        if hasattr(self, "waybill_image_filter"):
            self.waybill_image_filter.setCurrentText("全部")
        if hasattr(self, "waybill_text_filter"):
            self.waybill_text_filter.clear()
        self.apply_waybill_parse_filter()

    def apply_waybill_parse_filter(self):
        if not hasattr(self, "waybill_parse_table"):
            return
        table = self.waybill_parse_table
        status_filter = self.waybill_image_filter.currentText() if hasattr(self, "waybill_image_filter") else "全部"
        keyword = normalize_text(self.waybill_text_filter.text()).casefold() if hasattr(self, "waybill_text_filter") else ""
        status_col = RAW_PIPELINE_INTERNAL_FIELDS.index(WAYBILL_IMAGE_STATUS_FIELD)
        visible = 0
        total = table.rowCount()
        for row_index in range(total):
            status_item = table.item(row_index, status_col)
            status = status_item.text().strip() if status_item else ""
            status_ok = status_filter == "全部" or status == status_filter
            text_ok = True
            if keyword:
                parts = []
                for col in range(table.columnCount()):
                    item = table.item(row_index, col)
                    if item:
                        parts.append(item.text())
                text_ok = keyword in normalize_text(" ".join(parts)).casefold()
            hidden = not (status_ok and text_ok)
            table.setRowHidden(row_index, hidden)
            if not hidden:
                visible += 1
        if total:
            self.statusBar().showMessage(f"面单解析筛选：显示 {visible}/{total} 行")

    def set_waybill_parse_rows(self, rows):
        rows = self.update_waybill_image_status(rows)
        sorting = self.waybill_parse_table.isSortingEnabled()
        self.waybill_parse_table.setSortingEnabled(False)
        self.waybill_parse_table.setRowCount(0)
        for row_index, row in enumerate(rows):
            self.waybill_parse_table.setRowCount(row_index + 1)
            for col, header in enumerate(RAW_PIPELINE_INTERNAL_FIELDS):
                item = QTableWidgetItem("" if row.get(header) is None else str(row.get(header, "")))
                self.waybill_parse_table.setItem(row_index, col, item)
        self.waybill_parse_table.setSortingEnabled(sorting)
        self.apply_waybill_parse_filter()
        self.waybill_parse_file_label.setText(
            f"{os.path.basename(self.waybill_parse_source_file) if self.waybill_parse_source_file else '未选择原始Excel'}    已识别 {len(rows)} 行"
        )

    def fill_blank_waybill_shoes(self):
        rows = self.collect_waybill_parse_rows()
        if not rows:
            show_info(self, "没有可处理数据", "请先打开面单 Excel。")
            return

        rules = self.system.get("waybill_parse_rules", {})
        original_col = RAW_PIPELINE_INTERNAL_FIELDS[-2]
        changed = 0
        parsed_cache = {}

        for row in rows:
            if row.get("商品简称", "").strip():
                continue

            raw_text = row.get(original_col, "").strip()
            parsed_rows = []
            if raw_text:
                if raw_text not in parsed_cache:
                    parsed_cache[raw_text] = parse_waybill_raw_text(raw_text, "", rules)
                parsed_rows = parsed_cache[raw_text]

            candidate = self.find_waybill_reparse_candidate(row, parsed_rows)
            if candidate:
                row["商品简称"] = candidate.get("商品简称", "")
                row["规格"] = candidate.get("规格", row.get("规格", ""))
                row["尺码"] = candidate.get("尺码", row.get("尺码", ""))
                row["数量"] = candidate.get("数量", row.get("数量", ""))
                row["解析状态"] = "已补识别"
                changed += 1
                continue

            shoe = (
                infer_shoe_from_spec(row.get("规格", ""), rules)
                or infer_shoe_from_shop_keyword(row.get("店铺关键词", ""), rules)
            )
            if shoe:
                row["商品简称"] = shoe
                row["规格"] = strip_rule_shoe_prefix(row.get("规格", ""), shoe, rules)
                row["解析状态"] = "已补识别"
                changed += 1

        if not changed:
            show_info(self, "没有可补识别内容", "当前表格没有按现有规则可补上的空白商品简称。")
            return
        self.set_waybill_parse_rows(rows)
        self.statusBar().showMessage(f"已补识别空白商品简称：{changed} 行")

    def find_waybill_reparse_candidate(self, row, candidates):
        if not candidates:
            return None
        spec = str(row.get("规格", "")).strip()
        size = str(row.get("尺码", "")).strip()
        qty = str(normalize_qty(row.get("数量", 1)))
        for candidate in candidates:
            if (
                str(candidate.get("规格", "")).strip() == spec
                and str(candidate.get("尺码", "")).strip() == size
                and str(normalize_qty(candidate.get("数量", 1))) == qty
                and str(candidate.get("商品简称", "")).strip()
            ):
                return candidate
        filled = [item for item in candidates if str(item.get("商品简称", "")).strip()]
        if len(filled) == 1:
            return filled[0]
        return None

    def open_waybill_parse_excel(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择面单Excel",
            "",
            "Excel文件 (*.xlsx *.xls);;所有文件 (*.*)",
        )
        if not file:
            return
        self.waybill_parse_source_file = file
        self.waybill_parse_saved_file = ""
        try:
            df = pd.read_excel(file)
            headers = {str(col).strip() for col in df.columns}
            current_fields = set(RAW_PIPELINE_INTERNAL_FIELDS)
            legacy_fields = set(RAW_PIPELINE_INTERNAL_FIELDS)
            legacy_fields.discard(WAYBILL_IMAGE_STATUS_FIELD)
            legacy_fields.add(LEGACY_WAYBILL_REMARK_FIELD)
            if current_fields.issubset(headers) or legacy_fields.issubset(headers):
                rows = []
                for _, row in df.iterrows():
                    item = {field: "" if pd.isna(row.get(field, "")) else str(row.get(field, "")) for field in RAW_PIPELINE_INTERNAL_FIELDS}
                    if WAYBILL_IMAGE_STATUS_FIELD not in headers and LEGACY_WAYBILL_REMARK_FIELD in headers:
                        item[WAYBILL_IMAGE_STATUS_FIELD] = ""
                    if any(item.values()):
                        rows.append(item)
                self.waybill_parse_saved_file = file
                self.set_waybill_parse_rows(rows)
                self.statusBar().showMessage(f"已打开识别结果：{len(rows)} 行")
                return
        except Exception as exc:
            show_error(self, "打开失败", exc)
            return
        self.reparse_waybill_source()

    def reparse_waybill_source(self):
        if not self.waybill_parse_source_file:
            show_info(self, "未选择文件", "请先打开采集到的原始 Excel。")
            return
        try:
            df = pd.read_excel(self.waybill_parse_source_file)
            raw_col = RAW_WAYBILL_TEXT_COLUMN
            if raw_col not in df.columns:
                original_col = RAW_PIPELINE_INTERNAL_FIELDS[-2]
                if original_col in df.columns:
                    raw_col = original_col
                elif not len(df.columns):
                    raise ValueError("Excel 没有可读取的列。")
                else:
                    raw_col = str(df.columns[0])
            template = {"mode": RAW_WAYBILL_MODE, "raw_text": raw_col}
            rows = parse_raw_waybill_dataframe(
                df,
                self.waybill_parse_source_file,
                template,
                self.system.get("waybill_parse_rules", {}),
            )
            self.set_waybill_parse_rows(rows)
            self.statusBar().showMessage(f"面单解析完成：{len(rows)} 行")
        except Exception as exc:
            show_error(self, "解析失败", exc)

    def collect_waybill_parse_rows(self):
        rows = []
        for row_index in range(self.waybill_parse_table.rowCount()):
            row = {}
            has_value = False
            for col, header in enumerate(RAW_PIPELINE_INTERNAL_FIELDS):
                item = self.waybill_parse_table.item(row_index, col)
                value = item.text().strip() if item else ""
                row[header] = value
                if value:
                    has_value = True
            if has_value:
                if not row.get("解析状态"):
                    row["解析状态"] = "手动修正"
                rows.append(row)
        return rows

    def default_waybill_parse_save_path(self):
        out_dir = Path(get_output_dir())
        out_dir.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        return out_dir / f"监控面单识别_手动修正_{ts}.xlsx"

    def save_waybill_parse_edits(self):
        rows = self.collect_waybill_parse_rows()
        if not rows:
            show_info(self, "没有可保存数据", "请先打开原始 Excel 并完成识别或手动填写。")
            return
        try:
            rows = self.update_waybill_image_status(rows)
            self.set_waybill_parse_rows(rows)
            learned = self.learn_waybill_rules_from_rows(rows)
            path = Path(self.waybill_parse_saved_file) if self.waybill_parse_saved_file else self.default_waybill_parse_save_path()
            write_processed_waybill_xlsx(rows, path)
            self.waybill_parse_saved_file = str(path)
            self.waybill_parse_file_label.setText(f"{os.path.basename(self.waybill_parse_source_file) if self.waybill_parse_source_file else '识别结果'}    已保存 {len(rows)} 行")
            message = str(path)
            if learned:
                message += f"\n\n已自动学习 {learned} 个面单识别关键词，后续长期生效。"
            show_info(self, "保存完成", message)
            self.statusBar().showMessage(f"面单识别结果已保存：{path}")
        except Exception as exc:
            show_error(self, "保存失败", exc)

    def export_waybill_parse_excel(self):
        rows = self.collect_waybill_parse_rows()
        if not rows:
            show_info(self, "没有可导出数据", "请先打开原始 Excel 并完成识别或手动填写。")
            return
        try:
            rows = self.update_waybill_image_status(rows)
            self.set_waybill_parse_rows(rows)
            path = self.default_waybill_parse_save_path()
            write_processed_waybill_xlsx(rows, path)
            self.waybill_parse_saved_file = str(path)
            show_info(self, "另存完成", str(path))
            self.statusBar().showMessage(f"识别Excel已另存：{path}")
        except Exception as exc:
            show_error(self, "导出失败", exc)

    def render_stalls(self):
        stall_map = self.system.get("stall_map", {}) or {}
        shoes = self.known_shoe_names()
        if not shoes:
            shoes = sorted(stall_map.keys(), key=lambda item: str(item).casefold())
        self.stall_table.setRowCount(0)
        for row, shoe in enumerate(shoes):
            set_table_row(self.stall_table, row, [shoe, stall_map.get(shoe, "")])

    def load_selected_stall(self):
        row = selected_row(self.stall_table)
        if row < 0:
            return
        self.stall_category.setText(self.stall_table.item(row, 0).text())
        self.stall_value.setText(self.stall_table.item(row, 1).text())
        self.stall_state_title.setText(f"正在编辑：{self.stall_category.text()}")
        self.stall_state_detail.setText(f"生成订单时会归入鞋款档口：{self.stall_value.text() or '未设置'}")

    def save_stall(self):
        category = self.stall_category.text().strip()
        stall = self.stall_value.text().strip()
        if not category or not stall:
            show_info(self, "缺少内容", "鞋款和鞋款档口不能为空。")
            return
        self.system.setdefault("stall_map", {})[category] = stall
        self.persist()
        self.render_stalls()
        self.stall_state_title.setText(f"已保存：{category}")
        self.stall_state_detail.setText(f"生成订单时会归入鞋款档口：{stall}")

    def delete_stall(self):
        category = self.stall_category.text().strip()
        if category and category in self.system.setdefault("stall_map", {}):
            self.system["stall_map"].pop(category, None)
            self.persist()
            self.render_stalls()
            self.clear_stall_form()

    def clear_stall_form(self):
        self.stall_category.clear()
        self.stall_value.clear()
        self.stall_table.clearSelection()
        self.stall_state_title.setText("准备新增鞋款档口")
        self.stall_state_detail.setText("从左侧选择鞋款可修改；直接填写鞋款和档口可新增。")

    def render_templates(self):
        templates = self.system.get("import_templates", [])
        self.template_table.setRowCount(0)
        for row, tpl in enumerate(templates):
            set_table_row(
                self.template_table,
                row,
                [
                    tpl.get("name", ""),
                    tpl.get("mode", ""),
                    tpl.get("short_name", "") or tpl.get("raw_text", ""),
                    tpl.get("spec", ""),
                    tpl.get("size", ""),
                    tpl.get("qty", ""),
                    tpl.get("remark", ""),
                ],
            )

    def _guess_excel_header(self, headers, keywords, excludes=()):
        cleaned = [str(h or "").strip() for h in headers if str(h or "").strip()]
        for keyword in keywords:
            keyword_l = keyword.lower()
            for header in cleaned:
                header_l = header.lower()
                if keyword_l in header_l and not any(x.lower() in header_l for x in excludes):
                    return header
        return ""

    def _read_xlsx_headers(self, path):
        with zipfile.ZipFile(path) as zf:
            shared = []
            if "xl/sharedStrings.xml" in zf.namelist():
                root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
                ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
                for item in root.findall("a:si", ns):
                    parts = [node.text or "" for node in item.findall(".//a:t", ns)]
                    shared.append("".join(parts))

            sheet_path = "xl/worksheets/sheet1.xml"
            try:
                workbook = ET.fromstring(zf.read("xl/workbook.xml"))
                rels = ET.fromstring(zf.read("xl/_rels/workbook.xml.rels"))
                wb_ns = {
                    "a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
                    "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
                }
                rel_ns = {"a": "http://schemas.openxmlformats.org/package/2006/relationships"}
                first_sheet = workbook.find("a:sheets/a:sheet", wb_ns)
                if first_sheet is not None:
                    rel_id = first_sheet.attrib.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
                    for rel in rels.findall("a:Relationship", rel_ns):
                        if rel.attrib.get("Id") == rel_id:
                            target = rel.attrib.get("Target", "")
                            if target.startswith("/"):
                                sheet_path = target.lstrip("/")
                            else:
                                sheet_path = "xl/" + target.lstrip("/")
                            break
            except Exception:
                pass

            sheet = ET.fromstring(zf.read(sheet_path))
            ns = {"a": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
            row = sheet.find("a:sheetData/a:row", ns)
            if row is None:
                return []

            headers = []
            for cell in row.findall("a:c", ns):
                cell_type = cell.attrib.get("t")
                text = ""
                if cell_type == "s":
                    value = cell.find("a:v", ns)
                    if value is not None and value.text is not None:
                        try:
                            text = shared[int(value.text)]
                        except Exception:
                            text = value.text
                elif cell_type == "inlineStr":
                    parts = [node.text or "" for node in cell.findall(".//a:t", ns)]
                    text = "".join(parts)
                else:
                    value = cell.find("a:v", ns)
                    text = value.text if value is not None and value.text is not None else ""
                text = str(text).strip()
                if text:
                    headers.append(text)
            return headers

    def detect_template_from_excel(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "选择样本Excel",
            "",
            "Excel 文件 (*.xlsx);;所有文件 (*.*)",
        )
        if not path:
            return

        try:
            headers = self._read_xlsx_headers(path)
        except Exception as exc:
            show_error(self, "读取失败", str(exc))
            return

        if not headers:
            show_info(self, "未检测到表头", "这个 Excel 没有读取到有效表头。")
            return

        short_col = self._guess_excel_header(
            headers,
            ["鞋款", "商品简称", "商品名称", "货品标题", "商品标题", "标题", "商品"],
            ["规格", "尺码", "数量", "备注", "留言"],
        )
        spec_col = self._guess_excel_header(
            headers,
            ["销售规格", "商品规格", "规格名称", "规格", "鞋款", "款式", "颜色分类", "颜色", "SKU", "sku"],
            ["尺码", "鞋码", "数量"],
        )
        size_col = self._guess_excel_header(
            headers,
            ["鞋码", "尺码", "码数", "size", "SIZE"],
            ["档口"],
        )
        qty_col = self._guess_excel_header(
            headers,
            ["商品数量", "购买数量", "下单数量", "数量", "件数"],
        )
        remark_col = self._guess_excel_header(
            headers,
            ["卖家备注", "商家备注", "订单备注", "买家备注", "买家留言", "客户备注", "备注", "留言"],
        )

        if not self.tpl_name.text().strip():
            self.tpl_name.setText(os.path.splitext(os.path.basename(path))[0])
        idx = self.tpl_mode.findText("表头")
        self.tpl_mode.setCurrentIndex(max(idx, 0))
        self.tpl_short_name.setText(short_col)
        self.tpl_spec.setText(spec_col)
        self.tpl_size.setText(size_col)
        self.tpl_qty.setText(qty_col)
        self.tpl_remark.setText(remark_col)
        self.tpl_title_col.clear()
        self.tpl_qty_col.clear()
        self.tpl_item_sep.setText(self.tpl_item_sep.text().strip() or ";")
        self.tpl_spec_split.setText(self.tpl_spec_split.text().strip() or "，")

        missing = []
        if not short_col:
            missing.append("鞋款")
        if not spec_col:
            missing.append("规格/鞋款")
        if not qty_col:
            missing.append("数量")

        detail = (
            f"鞋款：{short_col or '未识别'}    规格：{spec_col or '未识别'}    "
            f"尺码：{size_col or '未单独识别'}    数量：{qty_col or '未识别'}"
        )
        self.template_state_title.setText("Excel表头识别完成")
        self.template_state_detail.setText(detail)
        if missing:
            show_info(self, "识别完成但需检查", "未自动识别：" + "、".join(missing) + "。请手动补齐后再保存模板。")
        else:
            show_info(self, "识别完成", "已读取 Excel 表头并填入模板字段；检查无误后点击“新增/更新”保存。")

    def load_selected_template(self):
        row = selected_row(self.template_table)
        templates = self.system.get("import_templates", [])
        if row < 0 or row >= len(templates):
            return
        tpl = templates[row]
        self.tpl_name.setText(tpl.get("name", ""))
        idx = self.tpl_mode.findText(tpl.get("mode", "表头"))
        self.tpl_mode.setCurrentIndex(max(idx, 0))
        self.tpl_short_name.setText(tpl.get("short_name", "") or tpl.get("raw_text", ""))
        self.tpl_spec.setText(tpl.get("spec", ""))
        self.tpl_size.setText(tpl.get("size", ""))
        self.tpl_qty.setText(tpl.get("qty", ""))
        self.tpl_remark.setText(tpl.get("remark", ""))
        self.tpl_title_col.setText(tpl.get("title_col", ""))
        self.tpl_qty_col.setText(tpl.get("qty_col", ""))
        self.tpl_item_sep.setText(tpl.get("item_sep", ";"))
        self.tpl_spec_split.setText(tpl.get("spec_split", "，"))
        self.template_state_title.setText(f"正在编辑：{tpl.get('name', '')}")
        if tpl.get("mode") == RAW_WAYBILL_MODE:
            self.template_state_detail.setText(
                f"模式：{RAW_WAYBILL_MODE}    原文字段：{tpl.get('raw_text', '') or tpl.get('short_name', '') or RAW_WAYBILL_TEXT_COLUMN}"
            )
        else:
            self.template_state_detail.setText(
                f"模式：{tpl.get('mode', '表头')}    鞋款：{tpl.get('short_name', '') or tpl.get('title_col', '')}    规格：{tpl.get('spec', '') or tpl.get('title_col', '')}    尺码：{tpl.get('size', '') or '规格内拆分'}"
            )

    def save_template(self):
        name = self.tpl_name.text().strip()
        if not name:
            show_info(self, "缺少内容", "模板名不能为空。")
            return
        tpl = {
            "name": name,
            "mode": self.tpl_mode.currentText(),
            "short_name": self.tpl_short_name.text().strip(),
            "spec": self.tpl_spec.text().strip(),
            "size": self.tpl_size.text().strip(),
            "qty": self.tpl_qty.text().strip(),
            "remark": self.tpl_remark.text().strip(),
            "title_col": self.tpl_title_col.text().strip(),
            "qty_col": self.tpl_qty_col.text().strip(),
            "item_sep": self.tpl_item_sep.text().strip() or ";",
            "spec_split": self.tpl_spec_split.text().strip() or "，",
        }
        if tpl["mode"] == RAW_WAYBILL_MODE:
            tpl["raw_text"] = tpl["short_name"] or RAW_WAYBILL_TEXT_COLUMN
            tpl["short_name"] = tpl["raw_text"]
            tpl["spec"] = ""
            tpl["size"] = ""
            tpl["qty"] = ""
            tpl["remark"] = ""
        templates = self.system.setdefault("import_templates", [])
        row = selected_row(self.template_table)
        if row >= 0 and row < len(templates):
            templates[row] = tpl
        else:
            templates.append(tpl)
        self.system["active_template"] = templates[0].get("name", "") if templates else ""
        self.persist()
        self.render_templates()
        self.template_state_title.setText(f"已保存：{name}")
        if tpl["mode"] == RAW_WAYBILL_MODE:
            self.template_state_detail.setText(f"模式：{tpl['mode']}    原文字段：{tpl['raw_text']}")
        else:
            self.template_state_detail.setText(f"模式：{tpl['mode']}    规格字段：{tpl['spec'] or tpl['title_col'] or '未设置'}    尺码字段：{tpl['size'] or '规格内拆分'}")

    def delete_template(self):
        row = selected_row(self.template_table)
        templates = self.system.setdefault("import_templates", [])
        if row >= 0 and row < len(templates):
            templates.pop(row)
            self.system["active_template"] = templates[0].get("name", "") if templates else ""
            self.persist()
            self.render_templates()
            self.clear_template_form()

    def clear_template_form(self):
        for widget in [
            self.tpl_name,
            self.tpl_short_name,
            self.tpl_spec,
            self.tpl_size,
            self.tpl_qty,
            self.tpl_remark,
            self.tpl_title_col,
            self.tpl_qty_col,
            self.tpl_item_sep,
            self.tpl_spec_split,
        ]:
            widget.clear()
        self.tpl_mode.setCurrentIndex(0)
        self.template_table.clearSelection()
        self.template_state_title.setText("准备新增模板")
        self.template_state_detail.setText("从左侧选择模板可修改；新增模板建议先复制已有模板字段再微调。")

    def refresh_image_categories(self):
        current = self.image_category_filter.currentText()
        self.image_category_filter.clear()
        self.image_category_filter.addItem("全部鞋款")
        self.image_category_filter.addItems(self.known_shoe_names())
        idx = self.image_category_filter.findText(current)
        if idx >= 0:
            self.image_category_filter.setCurrentIndex(idx)

    def render_images(self):
        category = self.image_category_filter.currentText()
        if category in {"全部鞋款", "全部鞋款分类", "全部分类"}:
            category = ""
        keyword = self.image_keyword.text().strip()
        self.image_table.setRowCount(0)
        for row, (_, item) in enumerate(iter_image_bindings(category, keyword, max_items=1500)):
            aliases = "；".join(normalize_image_aliases(item.get("aliases", [])))
            set_table_row(
                self.image_table,
                row,
                [
                    item.get("category", ""),
                    item.get("spec", ""),
                    aliases,
                    item.get("image_file", ""),
                ],
            )
        stats = image_storage_summary(count_entries=False)
        self.statusBar().showMessage(
            f"图片关系已刷新：鞋款分类文件 {stats.get('category_files', 0)} 个，图片 {stats.get('image_files', 0)} 个"
        )

    def _sku_image_tool_args(self, **kwargs):
        defaults = {
            "out": "",
            "input": "",
            "inputs": [],
            "image_dir": "",
            "report": "",
            "dry_run": False,
            "no_backup": False,
            "no_download": False,
            "timeout": DEFAULT_TIMEOUT,
            "max_image_mb": DEFAULT_MAX_IMAGE_MB,
            "category_col": "",
            "spec_col": "",
            "aliases_col": "",
            "image_path_col": "",
            "image_url_col": "",
            "title_col": "",
            "remark_col": "",
            "platform_col": "",
            "product_id_col": "",
            "default_category": "",
        }
        defaults.update(kwargs)
        return SimpleNamespace(**defaults)

    def create_sku_image_template(self):
        try:
            path = create_sku_image_template_file(self._sku_image_tool_args())
            self.statusBar().showMessage(f"SKU图片绑定模板已生成：{path}")
            show_info(self, "模板已生成", str(path))
            open_file_or_folder(str(path))
        except Exception as exc:
            show_error(self, "生成模板失败", exc)

    def run_sku_image_import(self, dry_run=False):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择SKU图片绑定表",
            "",
            "Excel/CSV 文件 (*.xlsx *.xls *.csv);;所有文件 (*.*)",
        )
        if not file:
            return
        image_dir = QFileDialog.getExistingDirectory(
            self,
            "选择图片目录（可取消，仅使用表格路径或图片链接）",
            os.path.dirname(file),
        )
        try:
            args = self._sku_image_tool_args(
                input=file,
                image_dir=image_dir,
                dry_run=dry_run,
            )
            counters, report_path = import_sku_image_bindings_file(args)
            if not dry_run:
                self.reload_data()
            title = "预览完成" if dry_run else "批量导入完成"
            message = (
                f"总行数：{counters['total']}\n"
                f"已导入：{counters['imported']}\n"
                f"可导入：{counters.get('would_import', 0)}\n"
                f"跳过：{counters['skipped']}\n"
                f"失败：{counters['failed']}\n\n"
                f"报告：{report_path}"
            )
            show_info(self, title, message)
            open_file_or_folder(str(report_path))
        except Exception as exc:
            show_error(self, "批量处理失败", exc)

    def create_missing_image_report(self):
        files, _ = QFileDialog.getOpenFileNames(
            self,
            "选择订单/面单识别文件",
            "",
            "Excel/CSV 文件 (*.xlsx *.xls *.csv);;所有文件 (*.*)",
        )
        if not files:
            return
        try:
            summary, report_path = create_missing_image_report_file(
                self._sku_image_tool_args(inputs=files)
            )
            show_info(
                self,
                "缺图清单已生成",
                f"检查行数：{summary['total_rows']}\n"
                f"已匹配行数：{summary['matched_rows']}\n"
                f"缺图SKU数：{summary['missing_unique']}\n\n"
                f"报告：{report_path}",
            )
            open_file_or_folder(str(report_path))
        except Exception as exc:
            show_error(self, "生成缺图清单失败", exc)

    def load_selected_image(self):
        row = selected_row(self.image_table)
        if row < 0:
            return
        category = self.image_table.item(row, 0).text()
        spec = self.image_table.item(row, 1).text()
        aliases = self.image_table.item(row, 2).text()
        image_file = self.image_table.item(row, 3).text()
        self.current_image = (category, spec)
        self.img_category.setText(category)
        self.img_spec.setText(spec)
        self.img_aliases.setText(aliases)
        self.img_path.setText(image_file)
        self.pending_image_path = ""
        self.image_preview.set_image(self.resolve_image_path(image_file), image_file)
        self.image_state_title.setText(f"正在编辑：{category} / {spec}")
        self.image_state_detail.setText(f"别名：{aliases or '无'}    图片：{image_file or '未绑定'}")

    def choose_image(self):
        file, _ = QFileDialog.getOpenFileName(
            self,
            "选择图片",
            "",
            "图片文件 (*.png *.jpg *.jpeg *.webp *.bmp);;所有文件 (*.*)",
        )
        if file:
            self.set_image_file(file)

    def set_image_file(self, file):
        if not file:
            return
        self.pending_image_path = file
        self.img_path.setText(file)
        self.image_preview.set_image(file, os.path.basename(file))
        self.image_state_title.setText("图片已载入预览")
        self.image_state_detail.setText("确认鞋款分类、规格和别名后，点击“新增/更新”写入图片库。")
        self.statusBar().showMessage("图片已载入预览，点击新增/更新后写入图片库")

    def resolve_image_path(self, image_file):
        image_file = str(image_file or "").strip()
        if not image_file:
            return ""
        if os.path.isabs(image_file):
            return image_file
        candidate = os.path.join(get_data_dir(), image_file.replace("/", os.sep))
        if os.path.exists(candidate):
            return candidate
        return image_file

    def save_image(self):
        category = self.img_category.text().strip()
        spec = self.img_spec.text().strip()
        aliases = normalize_image_aliases(self.img_aliases.text())
        upload_path = self.pending_image_path.strip()
        if not category or not spec:
            show_info(self, "缺少内容", "鞋款和规格不能为空。")
            return
        try:
            old_image = self.current_image
            if upload_path and os.path.exists(upload_path):
                saved = upsert_image_binding(category, spec, source_path=upload_path, aliases=aliases)
                if old_image and old_image != (category, spec):
                    delete_image_binding(old_image[0], old_image[1])
            elif self.current_image:
                saved = update_image_binding(old_image[0], old_image[1], category, spec, aliases=aliases)
            else:
                show_info(self, "缺少图片", "新增图片关系时必须选择图片文件。")
                return
            self.refresh_image_categories()
            self.render_images()
            self.current_image = (category, spec)
            self.pending_image_path = ""
            image_file = saved.get("image_file", "")
            self.img_category.setText(category)
            self.img_spec.setText(spec)
            self.img_aliases.setText("；".join(normalize_image_aliases(saved.get("aliases", aliases))))
            self.img_path.setText(image_file)
            self.image_preview.set_image(self.resolve_image_path(image_file), image_file)
            self.render_dashboard()
            self.image_state_title.setText(f"已保存：{category} / {spec}")
            self.image_state_detail.setText(f"别名：{self.img_aliases.text() or '无'}    图片：{image_file or '未绑定'}")
            self.statusBar().showMessage("图片关系已保存")
        except Exception as exc:
            show_error(self, "保存图片关系失败", exc)

    def delete_image(self):
        category = self.img_category.text().strip()
        spec = self.img_spec.text().strip()
        if not category or not spec:
            return
        if delete_image_binding(category, spec):
            self.refresh_image_categories()
            self.render_images()
            self.clear_image_form()
            self.render_dashboard()

    def clear_image_form(self):
        self.current_image = None
        self.pending_image_path = ""
        self.img_category.clear()
        self.img_spec.clear()
        self.img_aliases.clear()
        self.img_path.clear()
        self.image_preview.set_image("")
        self.image_table.clearSelection()
        self.image_state_title.setText("准备新增图片绑定")
        self.image_state_detail.setText("从左侧选择记录可预览和替换图片；也可以拖入图片后保存为新绑定。")

    def backup_data(self):
        try:
            out = backup_data_file()
            if out:
                show_info(self, "备份完成", out)
            else:
                show_info(self, "没有可备份数据", "当前主数据文件不存在。")
        except Exception as exc:
            show_error(self, "备份失败", exc)

    def render_settings(self):
        self.settings_box.setPlainText(
            f"{APP_VERSION}\n"
            f"版本形态：{APP_EDITION}\n\n"
            f"主数据文件：{get_data_file()}\n"
            f"数据目录：{get_data_dir()}\n"
            f"图片文件目录：{get_images_dir()}\n"
            f"图片索引目录：{get_image_category_dir()}\n"
            f"输出目录：{get_output_dir()}\n\n"
            "操作规范：调试版只读写共享 data/output；敲定版本后再调整版本号并输出归档。"
        )


def main():
    app = QApplication(sys.argv)
    apply_app_style(app)
    guard = SingleInstanceGuard("admin", app)
    if not guard.start_or_notify():
        sys.exit(0)
    window = AdminWindow()
    guard.activated.connect(lambda: activate_window(window))
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
