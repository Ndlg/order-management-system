from dataclasses import dataclass


SHOE_FIELD = "鞋款"
SPEC_FIELD = "规格"
SIZE_FIELD = "尺码"
QUANTITY_FIELD = "数量"
REMARK_FIELD = "备注"
RAW_SHOE_FIELD = "原始鞋款"
RAW_SPEC_FIELD = "原始规格"
LEGACY_SHORT_NAME_FIELD = "商品简称"
LEGACY_TITLE_FIELD = "货品标题"
SOURCE_FILE_FIELD = "来源文件"

FIVE_FIELDS = [SHOE_FIELD, SPEC_FIELD, SIZE_FIELD, QUANTITY_FIELD, REMARK_FIELD]


def clean_cell_text(value):
    if value is None:
        return ""
    text = str(value).strip()
    if text.lower() == "nan":
        return ""
    return text


def normalize_quantity(value):
    text = clean_cell_text(value)
    if not text:
        return 1
    try:
        number = float(text)
        if number.is_integer():
            return int(number)
        return number
    except Exception:
        return text


@dataclass
class FiveFieldItem:
    shoe: str
    spec: str
    size: str
    quantity: object
    remark: str = ""
    source_file: str = ""
    raw_shoe: str = ""
    raw_spec: str = ""
    raw_text: str = ""

    def title_text(self):
        return self.raw_text or f"{self.shoe} 颜色: {self.spec} 尺码: {self.size}"

    def to_order_row(self):
        """
        V7.8.0 入口标准行。
        前五列是新主流程要维护的五要素；旧字段继续镜像，保证后续档口和图片逻辑可逐步迁移。
        """
        return {
            SHOE_FIELD: self.shoe,
            SPEC_FIELD: self.spec,
            SIZE_FIELD: self.size,
            QUANTITY_FIELD: self.quantity,
            REMARK_FIELD: self.remark,
            RAW_SHOE_FIELD: self.raw_shoe or self.shoe,
            RAW_SPEC_FIELD: self.raw_spec or self.spec,
            LEGACY_SHORT_NAME_FIELD: self.shoe,
            LEGACY_TITLE_FIELD: self.title_text(),
            SOURCE_FILE_FIELD: self.source_file,
        }


def make_five_field_item(shoe, spec, size, quantity, remark="", source_file="", raw_shoe="", raw_spec="", raw_text=""):
    return FiveFieldItem(
        shoe=clean_cell_text(shoe),
        spec=clean_cell_text(spec),
        size=clean_cell_text(size),
        quantity=normalize_quantity(quantity),
        remark=clean_cell_text(remark),
        source_file=clean_cell_text(source_file),
        raw_shoe=clean_cell_text(raw_shoe),
        raw_spec=clean_cell_text(raw_spec),
        raw_text=clean_cell_text(raw_text),
    )
