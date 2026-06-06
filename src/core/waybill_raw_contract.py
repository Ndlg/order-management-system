from __future__ import annotations


RAW_WAYBILL_TEMPLATE_NAME = "监控面单-原文模式"
PROCESSED_WAYBILL_TEMPLATE_NAME = "监控面单-识别结果模式"
LEGACY_RAW_WAYBILL_TEMPLATE_NAMES = ("监控面单-表头模式",)
RAW_WAYBILL_MODE = "面单原文"
RAW_WAYBILL_TEXT_COLUMN = "打印信息"

AUXILIARY_WAYBILL_FIELDS = ["店铺名", "店铺关键词", "面单模式"]
WAYBILL_IMAGE_STATUS_FIELD = "图片识别"
LEGACY_WAYBILL_REMARK_FIELD = "备注"
PROCESSED_WAYBILL_FIELDS = ["商品简称", "规格", "尺码", "数量", WAYBILL_IMAGE_STATUS_FIELD]
RAW_WAYBILL_TRACKING_FIELDS = ["任务ID", "文档ID", "任务时间", "采集端ID", "来源机器", "来源序号"]
RAW_PIPELINE_INTERNAL_FIELDS = AUXILIARY_WAYBILL_FIELDS + PROCESSED_WAYBILL_FIELDS + RAW_WAYBILL_TRACKING_FIELDS + ["原始打印信息", "解析状态"]


def raw_waybill_template_names() -> set[str]:
    return {RAW_WAYBILL_TEMPLATE_NAME, *LEGACY_RAW_WAYBILL_TEMPLATE_NAMES}


def is_raw_waybill_template_name(value: object) -> bool:
    return str(value or "").strip() in raw_waybill_template_names()


def raw_waybill_text_column(template: dict | None = None) -> str:
    template = template or {}
    return str(
        template.get("raw_text")
        or template.get("print_text")
        or template.get("short_name")
        or RAW_WAYBILL_TEXT_COLUMN
    ).strip()
