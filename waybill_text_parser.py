from __future__ import annotations

import re


OUTPUT_FIELDS = ["店铺名", "店铺关键词", "面单模式", "商品简称", "规格", "尺码", "数量", "备注"]
PARSE_STATUS_FIELD = "_parse_status"

MODE_SHOP_CODE = "店铺码模式"
MODE_TITLE = "标题模式"
MODE_DIRECT_SHOP_PRINT = "店铺直接打单模式"
MODE_UNKNOWN = "未知模式"

SIZE_TOKEN_RE = r"(?:3[5-9]|4[0-9]|5[0-2])(?:\.5)?"
SIZE_LABELS = ("鞋码", "尺码", "码数", "size")
SPEC_LABELS = ("颜色分类", "销售规格", "商品规格", "规格", "颜色", "款式", "鞋款", "sku", "货号")
WEAK_SPEC_VALUES = {"", "未知", "无", "无规格", "默认", "默认规格", "均码", "拍下备注", "看备注"}
PSEUDO_SIZE_VALUES = {"默认", "均码", "看备注", "拍下备注"}
SHOP_NAME_RE = re.compile(r"(?P<shop>(?:秒|范|小)\s*\d+)", flags=re.I)
YEAR_STYLE_RE = re.compile(r"^\s*【?\s*\d{4}\s*(?:新款|新品)?\s*[^】\]]*[】\]]?\s*")
SPEC_TRAILING_NOISE_RE = re.compile(
    r"(?:跑步鞋|女鞋|男鞋|运动鞋|网面|夏季|春季|秋季|冬季|透气|轻潮|减震|休闲|复古|百搭|系带|厚底|情侣鞋|老爹鞋)+$"
)

TRACKING_NOISE_RE = re.compile(
    r"(?:运单号|快递单号|物流单号|订单号|业务机|打印机)\s*[:：=]?\s*(?:\[[^\]]*\]|【[^】]*】|[^,，;；\n]*)",
    flags=re.I,
)
KEY_VALUE_LINE_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*\s*[:：]")
ITEM_INFO_LINE_RE = re.compile(r"^ITEM_INFO\s*[:：]\s*(?P<value>.*)$", flags=re.I)
ITEM_TOTAL_COUNT_RE = re.compile(r"(?:^|\n)ITEM_TOTAL_COUNT\s*[:：]\s*(?P<qty>\d+)", flags=re.I)
ITEM_INFO_ITEM_RE = re.compile(
    rf"(?P<title>.+?)(?:[;；,\n]\s*|\s+)(?P<size>{SIZE_TOKEN_RE})\s*"
    r"(?:(?:[【\[\(（]\s*(?P<qty_bracket>\d+)\s*(?:件|双)?\s*[】\]\)）])|"
    r"(?:[*xX]\s*(?P<qty_x>\d+))|"
    r"(?:(?P<qty_plain>\d+)\s*(?:件|双)?))?",
    flags=re.I | re.S,
)
ITEM_INFO_SPEC_TAIL_RE = re.compile(
    r"(?P<shoe>[A-Za-z]*\d+(?:\.\d+)?)\s*(?P<spec>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9/_ -]*)$",
    flags=re.I,
)

KNOWN_PREFIXES = ()
SPEC_SHOE_PREFIXES = ()
TITLE_SHOE_RULES = []
SPEC_KEYWORD_RULES = []
SHOP_KEYWORD_RULES = []


def split_rule_values(value: object) -> list[str]:
    if isinstance(value, (list, tuple, set)):
        parts = []
        for item in value:
            parts.extend(split_rule_values(item))
        return parts
    text = clean_cell(value)
    if not text:
        return []
    result = []
    for item in re.split(r"[\n,，、;；/|]+", text):
        item = clean_cell(item)
        if item and item not in result:
            result.append(item)
    return result


def copy_rule_items(rules: list[dict], prefix_key: str) -> list[dict]:
    items = []
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        shoe = clean_cell(rule.get("shoe") or rule.get("output_shoe") or rule.get("商品简称") or "")
        keywords = split_rule_values(rule.get("keywords") or rule.get("keyword") or rule.get("关键词") or "")
        prefixes = split_rule_values(rule.get(prefix_key) or rule.get("strip_prefixes") or rule.get("spec_prefixes") or rule.get("清洗词") or "")
        if not shoe or not keywords:
            continue
        item = {"shoe": shoe, "keywords": keywords}
        if prefixes:
            item[prefix_key] = prefixes
        items.append(item)
    return items


def default_rule_config() -> dict:
    return {
        "spec_keyword_rules": [],
        "shop_keyword_rules": [],
        "title_shoe_rules": [],
    }


def normalize_rule_config(config: object | None = None) -> dict:
    if not isinstance(config, dict):
        return default_rule_config()
    if isinstance(config.get("waybill_parse_rules"), dict):
        config = config.get("waybill_parse_rules") or {}

    return {
        "spec_keyword_rules": copy_rule_items(config.get("spec_keyword_rules", []), "strip_prefixes"),
        "shop_keyword_rules": copy_rule_items(config.get("shop_keyword_rules", []), "strip_prefixes"),
        "title_shoe_rules": copy_rule_items(config.get("title_shoe_rules", []), "spec_prefixes"),
    }


def detect_waybill_mode(value: object) -> str:
    text = strip_tracking_noise(value)
    if SHOP_NAME_RE.search(text):
        return MODE_SHOP_CODE
    if re.search(r"[【\[].+?[】\]]", text) and re.search(rf"\s{SIZE_TOKEN_RE}\s+\d+\s*(?:件|双|对)?\s*$", text, flags=re.I | re.M):
        return MODE_TITLE
    return MODE_UNKNOWN


def normalize_raw_text(value: object) -> str:
    text = str(value or "")
    text = text.replace("\u3000", " ").replace("\r", "\n")
    text = text.replace("，", ",").replace("、", ",")
    text = text.replace("；", "\n").replace(";", "\n")
    text = text.replace("×", "x").replace("Ｘ", "x").replace("ｘ", "x")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = re.sub(r",{2,}", ",,", text)
    return text.strip(" ,\n")


def strip_tracking_noise(value: object) -> str:
    text = normalize_raw_text(value)
    previous = None
    while previous != text:
        previous = text
        text = TRACKING_NOISE_RE.sub("", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\s*\n\s*", "\n", text)
    return text.strip(" ,\n")


def clean_cell(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "null", "undefined"}:
        return ""
    return re.sub(r"\s+", " ", text).strip(" ,，;；")


def compact_match_text(value: object) -> str:
    text = clean_cell(value).casefold()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def normalize_shop_name(value: object) -> str:
    return re.sub(r"\s+", "", clean_cell(value))


def split_shop_name(value: object) -> tuple[str, str]:
    text = clean_cell(value)
    match = SHOP_NAME_RE.search(text)
    if not match:
        return "", text
    shop = normalize_shop_name(match.group("shop"))
    remainder = clean_cell(f"{text[:match.start()]} {text[match.end():]}")
    return shop, remainder


def shop_hint_from_remainder(value: object) -> str:
    text = normalize_raw_text(value).replace("\n", ",")
    for token in [clean_cell(item) for item in text.split(",")]:
        if token and token not in WEAK_SPEC_VALUES and not re.search(r"[*xX]\s*\d+\s*$", token):
            return clean_cell(token)
    return ""


def normalize_size(value: object) -> str:
    text = clean_cell(value)
    if re.fullmatch(r"\d+\.0", text):
        text = text[:-2]
    if re.fullmatch(SIZE_TOKEN_RE, text):
        return text
    return ""


def normalize_qty(value: object) -> int:
    match = re.search(r"\d+", str(value or ""))
    if not match:
        return 1
    try:
        return max(1, int(match.group(0)))
    except Exception:
        return 1


def clean_spec(value: object) -> str:
    text = clean_cell(value)
    for label in (*SPEC_LABELS, *SIZE_LABELS):
        text = re.sub(rf"^{re.escape(label)}\s*[:：=]\s*", "", text, flags=re.I).strip()
    text = re.sub(r"^\d+\.\d+\s*", "", text).strip()
    return "" if text in WEAK_SPEC_VALUES else text


def clean_item_info_spec(value: object) -> str:
    text = clean_cell(value)
    for label in (*SPEC_LABELS, *SIZE_LABELS):
        text = re.sub(rf"^{re.escape(label)}\s*[:：=]\s*", "", text, flags=re.I).strip()
    return "" if text in WEAK_SPEC_VALUES else text


def strip_trailing_style_code(value: object) -> str:
    text = clean_cell(value)
    text = re.sub(
        r"(?<=[\u4e00-\u9fff])\s*[A-Z]?\d{4,}[A-Z]*(?:[-_ ]+[A-Z]?\d{4,}[A-Z]*)*\s*$",
        "",
        text,
        flags=re.I,
    )
    return clean_cell(text)


def infer_shoe_from_spec(spec: object, rule_config: object | None = None) -> str:
    text = compact_match_text(spec)
    if not text:
        return ""
    for rule in normalize_rule_config(rule_config).get("spec_keyword_rules", []):
        for keyword in rule.get("keywords", ()):
            marker = compact_match_text(keyword)
            if marker and marker in text:
                return str(rule.get("shoe") or "").strip()
    return ""


def infer_shoe_from_shop_keyword(keyword: object, rule_config: object | None = None) -> str:
    text = compact_match_text(keyword)
    if not text:
        return ""
    for rule in normalize_rule_config(rule_config).get("shop_keyword_rules", []):
        for item in rule.get("keywords", ()):
            marker = compact_match_text(item)
            if marker and (marker == text or (len(marker) >= 2 and marker in text)):
                return str(rule.get("shoe") or "").strip()
    return ""


def strip_rule_shoe_prefix(spec: object, shoe: str, rule_config: object | None = None) -> str:
    text = clean_spec(spec)
    if not text or not shoe:
        return text

    prefixes = [shoe]
    for rule in normalize_rule_config(rule_config).get("spec_keyword_rules", []):
        if rule.get("shoe") == shoe:
            prefixes.extend(rule.get("strip_prefixes", ()))

    for prefix in sorted({item for item in prefixes if item}, key=len, reverse=True):
        text = re.sub(rf"^{re.escape(prefix)}\s*[-_/ ]*", "", text, flags=re.I).strip()
    return clean_spec(text)


def strip_title_noise(value: object) -> str:
    text = clean_cell(value)
    text = re.sub(r"^[【\[][^】\]]+[】\]]\s*", "", text)
    text = YEAR_STYLE_RE.sub("", text)
    return clean_cell(text)


def title_rule_matches(rule: dict, value: object) -> bool:
    compact = compact_match_text(value)
    if not compact:
        return False
    for keyword in rule.get("keywords", ()):
        marker = compact_match_text(keyword)
        if marker and marker in compact:
            return True
    return False


def apply_title_rule(rule: dict, spec_text: object) -> tuple[str, str]:
    shoe = str(rule.get("shoe") or "").strip()
    spec = clean_cell(spec_text)
    for prefix in rule.get("spec_prefixes", ()):
        spec = re.sub(rf"^\s*{re.escape(prefix)}\s*", "", spec, flags=re.I)
    spec = strip_trailing_style_code(spec)
    spec = SPEC_TRAILING_NOISE_RE.sub("", spec)
    return shoe, clean_spec(spec)


def split_title_shoe_and_spec(title: object, rule_config: object | None = None) -> tuple[str, str]:
    full_text = clean_cell(title)
    spec_text = strip_title_noise(full_text)
    rules = normalize_rule_config(rule_config).get("title_shoe_rules", [])
    for rule in rules:
        if title_rule_matches(rule, spec_text):
            return apply_title_rule(rule, spec_text)
    for rule in rules:
        if title_rule_matches(rule, full_text):
            return apply_title_rule(rule, spec_text)
    return "", clean_spec(spec_text)


def split_shoe_from_spec(spec: object, fallback_shoe: object = "", rule_config: object | None = None) -> tuple[str, str]:
    text = clean_cell(spec)
    if not text:
        return "", ""

    shoe = infer_shoe_from_spec(text, rule_config)
    if shoe:
        return shoe, strip_rule_shoe_prefix(text, shoe, rule_config)

    for prefix in sorted(SPEC_SHOE_PREFIXES, key=len, reverse=True):
        match = re.match(rf"^{re.escape(prefix)}\s*[-_/ ]*(?P<rest>.*)$", text, flags=re.I)
        if match:
            return prefix, clean_spec(match.group("rest"))

    fallback = infer_shoe_from_shop_keyword(fallback_shoe, rule_config)
    return fallback, clean_spec(text)


def with_parse_mode(row: dict, mode: str) -> dict:
    item = dict(row)
    item.setdefault("店铺名", "")
    item.setdefault("店铺关键词", "")
    item["面单模式"] = mode
    return item


def clean_remark(value: object) -> str:
    parts = []
    for fragment in re.split(r"[;；\n]+", str(value or "")):
        item = strip_tracking_noise(fragment)
        item = clean_cell(item)
        if not item:
            continue
        if any(re.match(rf"^{re.escape(label)}\s*[:：=]", item, flags=re.I) for label in (*SPEC_LABELS, *SIZE_LABELS)):
            continue
        if item not in parts:
            parts.append(item)
    return "；".join(parts)


def split_known_prefix(body: str) -> tuple[str, str]:
    text = clean_cell(body)
    for prefix in KNOWN_PREFIXES:
        if text.lower().startswith(prefix.lower()):
            return prefix, clean_spec(text[len(prefix):])

    code_match = re.match(r"^(?P<shoe>(?:\d+\.\d+)?\s*(?:秒|范)\s*\d+[A-Za-z0-9]*(?:\s+[A-Za-z0-9][A-Za-z0-9.\-]*)?)(?P<spec>.*)$", text)
    if code_match:
        shoe = clean_cell(code_match.group("shoe"))
        spec = clean_spec(code_match.group("spec"))
        return shoe, spec

    return text, ""


def label_value(line: str, labels: tuple[str, ...]) -> tuple[str, str] | None:
    label_pattern = "|".join(re.escape(label) for label in labels)
    match = re.search(rf"(?:{label_pattern})\s*[:：=]\s*(?P<value>.+)$", clean_cell(line), flags=re.I)
    if not match:
        return None
    return match.group(0).split(match.group("value"), 1)[0], clean_cell(match.group("value"))


def parse_size_label_line(line: str) -> tuple[str, str, int] | None:
    label_pattern = "|".join(re.escape(label) for label in SIZE_LABELS)
    match = re.search(
        rf"(?P<body>.*?)(?:{label_pattern})\s*[:：=]\s*(?P<size>{SIZE_TOKEN_RE})(?:\s*[\[【(（][^\]】)）]*[\]】)）])?(?:\s*[*xX]\s*(?P<qty>\d+))?\s*$",
        clean_cell(line),
        flags=re.I,
    )
    if not match:
        return None
    body = clean_cell(match.group("body"))
    return body, normalize_size(match.group("size")), normalize_qty(match.group("qty") or 1)


def build_keyword_row(
    spec_text: object,
    size: object,
    qty: object = 1,
    shop_name: object = "",
    fallback_shoe: object = "",
    rule_config: object | None = None,
) -> dict | None:
    spec = clean_cell(spec_text)
    size_text = normalize_size(size)
    if not spec or not size_text:
        return None

    shoe, spec = split_shoe_from_spec(spec, fallback_shoe, rule_config)
    return {
        "店铺名": normalize_shop_name(shop_name),
        "店铺关键词": clean_cell(fallback_shoe),
        "面单模式": MODE_SHOP_CODE,
        "商品简称": clean_cell(shoe),
        "规格": spec,
        "尺码": size_text,
        "数量": normalize_qty(qty),
    }


def parse_labeled_item_groups(text: str, rule_config: object | None = None) -> list[dict]:
    source = strip_tracking_noise(text)
    if not source:
        return []

    rows = []
    pending_spec = ""
    current_shop = ""
    current_hint = ""
    for line in source.splitlines():
        item = clean_cell(line)
        if not item:
            continue

        shop, remainder = split_shop_name(item)
        if shop:
            current_shop = shop
            current_hint = shop_hint_from_remainder(remainder) or current_hint

        size_line = parse_size_label_line(item)
        if size_line:
            body, size, qty = size_line
            spec_text = clean_spec(body) or pending_spec
            row = build_keyword_row(spec_text, size, qty, current_shop, current_hint, rule_config)
            if row:
                rows.append(with_parse_mode(row, MODE_SHOP_CODE))
                pending_spec = ""
                continue

        spec_value = label_value(item, SPEC_LABELS)
        if spec_value:
            pending_spec = clean_spec(spec_value[1])
            continue

        candidate = clean_spec(item)
        if infer_shoe_from_spec(candidate, rule_config):
            pending_spec = candidate

    return rows


def split_glued_items(text: str) -> list[str]:
    source = strip_tracking_noise(text)
    if not source:
        return []

    source = re.sub(
        r"([*xX]\s*\d+)(?=\s*(?:秒|范)\s*\d|The\s*Roger|TheRoger|Cloud|ACG|AC\b)",
        r"\1\n",
        source,
        flags=re.I,
    )
    source = re.sub(
        rf"((?:{SIZE_TOKEN_RE}|默认|均码)\s*[*xX]\s*\d+)(?=[A-Za-z0-9\u4e00-\u9fff])",
        r"\1\n",
        source,
    )
    source = re.sub(
        rf"(,\s*{SIZE_TOKEN_RE})(?=\s*(?:\d+\.\d+\s|(?:秒|范)\s*\d|The\s*Roger|TheRoger|Cloud|ACG|AC\b))",
        r"\1\n",
        source,
        flags=re.I,
    )
    label_pattern = "|".join(re.escape(label) for label in SIZE_LABELS)
    source = re.sub(
        rf"((?:{label_pattern})\s*[:：=]?\s*{SIZE_TOKEN_RE})(?=[A-Za-z0-9\u4e00-\u9fff])",
        r"\1\n",
        source,
        flags=re.I,
    )

    segments = []
    for line in source.splitlines():
        item = clean_cell(line)
        if item:
            segments.append(item)
    return segments


def parse_labeled_size(segment: str, rule_config: object | None = None) -> dict | None:
    label_pattern = "|".join(re.escape(label) for label in SIZE_LABELS)
    match = re.search(
        rf"(?P<body>.+?)(?:{label_pattern})\s*[:：=]?\s*(?P<size>{SIZE_TOKEN_RE})(?:\s*[\[【(（][^\]】)）]*[\]】)）])?(?:\s*[*xX]\s*(?P<qty>\d+))?\s*$",
        segment,
        flags=re.I,
    )
    if not match:
        return None
    shop, body = split_shop_name(match.group("body"))
    shop_keyword = shop_hint_from_remainder(body)
    shoe, spec = split_shoe_from_spec(body, shop_keyword, rule_config)
    if not shoe:
        shoe, spec = split_known_prefix(body)
    return {
        "店铺名": shop,
        "店铺关键词": shop_keyword,
        "面单模式": MODE_SHOP_CODE if shop else MODE_UNKNOWN,
        "商品简称": shoe,
        "规格": spec,
        "尺码": normalize_size(match.group("size")),
        "数量": normalize_qty(match.group("qty") or 1),
    }


def parse_comma_segment(segment: str, rule_config: object | None = None) -> dict | None:
    normalized = normalize_raw_text(segment).replace("\n", ",")
    tokens = [clean_cell(token) for token in normalized.split(",") if clean_cell(token)]
    if not tokens:
        return None

    shop, shoe_hint = split_shop_name(tokens[0])
    shop_keyword = shop_hint_from_remainder(shoe_hint) or clean_cell(shoe_hint)
    spec_source = ""
    size = ""
    qty = 1

    last = tokens[-1]
    qty_match = re.search(r"(?P<value>.+?)\s*[*xX]\s*(?P<qty>\d+)\s*$", last)
    if qty_match:
        value = clean_cell(qty_match.group("value"))
        qty = normalize_qty(qty_match.group("qty"))
        size = normalize_size(value)
        if not size:
            if value in PSEUDO_SIZE_VALUES and len(tokens) >= 2:
                spec_source = tokens[-2]
            else:
                spec_source = value
        elif len(tokens) >= 2:
            before_size = clean_cell(last[: qty_match.start()].strip(" ,"))
            spec_source = before_size or tokens[-2]
    else:
        size_match = re.search(rf"(?P<size>{SIZE_TOKEN_RE})\s*$", last)
        if size_match:
            size = normalize_size(size_match.group("size"))
            spec_source = last[: size_match.start()] or (tokens[-2] if len(tokens) >= 2 else "")
        elif len(tokens) >= 2:
            spec_source = last

    if not spec_source and len(tokens) >= 2:
        spec_source = tokens[-2]
    shoe, spec = split_shoe_from_spec(spec_source, shop_keyword, rule_config)

    return {
        "店铺名": shop,
        "店铺关键词": shop_keyword,
        "面单模式": MODE_SHOP_CODE if shop else MODE_UNKNOWN,
        "商品简称": clean_cell(shoe),
        "规格": spec,
        "尺码": size,
        "数量": qty,
    }


def parse_space_segment(segment: str, rule_config: object | None = None) -> dict | None:
    text = normalize_raw_text(segment).replace("\n", " ")
    match = re.search(
        rf"(?P<body>.+?)\s+(?P<size>{SIZE_TOKEN_RE})\s*[*xX]\s*(?P<qty>\d+)\s*$",
        text,
        flags=re.I,
    )
    if not match:
        return None
    shop, body = split_shop_name(match.group("body"))
    shop_keyword = shop_hint_from_remainder(body)
    body = clean_cell(body)
    shoe, spec = split_shoe_from_spec(body, shop_keyword, rule_config)
    if not shoe:
        shoe, spec = split_known_prefix(body)
    if not spec and " " in body:
        shoe, spec = body.rsplit(" ", 1)
    return {
        "店铺名": shop,
        "店铺关键词": shop_keyword,
        "面单模式": MODE_SHOP_CODE if shop else MODE_UNKNOWN,
        "商品简称": clean_cell(shoe),
        "规格": clean_spec(spec),
        "尺码": normalize_size(match.group("size")),
        "数量": normalize_qty(match.group("qty")),
    }


def parse_title_quantity_segment(segment: str, rule_config: object | None = None) -> dict | None:
    text = clean_cell(strip_tracking_noise(segment))
    match = re.search(
        rf"(?P<title>.+?)\s+(?P<size>{SIZE_TOKEN_RE})(?:\s*[\[【(（][^\]】)）]*[\]】)）])?\s+(?P<qty>\d+)\s*(?:件|双|对)?\s*$",
        text,
        flags=re.I,
    )
    if not match:
        return None
    shoe, spec = split_title_shoe_and_spec(match.group("title"), rule_config)
    return {
        "店铺名": "",
        "店铺关键词": "",
        "面单模式": MODE_TITLE,
        "商品简称": shoe,
        "规格": spec,
        "尺码": normalize_size(match.group("size")),
        "数量": normalize_qty(match.group("qty")),
    }


def parse_spec_stuck_title_segment(segment: str, rule_config: object | None = None) -> dict | None:
    text = clean_cell(strip_tracking_noise(segment))
    match = re.search(
        rf"^(?P<spec>.+?)\s*,\s*(?P<size>{SIZE_TOKEN_RE})(?!\.5\s*[*xX])(?P<title>.+?)\s*[*xX]\s*(?P<qty>\d+)\s*$",
        text,
        flags=re.I,
    )
    if not match:
        return None

    spec_source = clean_cell(match.group("spec"))
    title = clean_cell(match.group("title"))
    shoe_from_spec, spec = split_shoe_from_spec(spec_source, "", rule_config)
    shoe_from_title, _title_spec = split_title_shoe_and_spec(title, rule_config)
    shoe = shoe_from_spec or shoe_from_title
    return {
        "店铺名": "",
        "店铺关键词": "",
        "面单模式": MODE_TITLE,
        "商品简称": clean_cell(shoe),
        "规格": spec if shoe_from_spec else clean_spec(spec_source),
        "尺码": normalize_size(match.group("size")),
        "数量": normalize_qty(match.group("qty")),
    }


def parse_spec_size_title_pairs(text: str, rule_config: object | None = None) -> list[dict]:
    lines = [clean_cell(line) for line in normalize_raw_text(text).splitlines() if clean_cell(line)]
    if len(lines) < 2:
        return []

    rules = normalize_rule_config(rule_config).get("title_shoe_rules", [])
    rows = []
    index = 0
    while index < len(lines) - 1:
        first = lines[index]
        second = lines[index + 1]
        first_match = re.match(rf"(?P<spec>.+?)\s*,\s*(?P<size>{SIZE_TOKEN_RE})\s*$", first, flags=re.I)
        if not first_match:
            index += 1
            continue

        matched_rule = None
        for rule in rules:
            if title_rule_matches(rule, second):
                matched_rule = rule
                break
        if not matched_rule:
            index += 1
            continue

        qty_match = re.search(r"[*xX]\s*(?P<qty>\d+)\s*$", second)
        rows.append(
            {
                "店铺名": "",
                "店铺关键词": "",
                "面单模式": MODE_TITLE,
                "商品简称": str(matched_rule.get("shoe") or "").strip(),
                "规格": clean_spec(first_match.group("spec")),
                "尺码": normalize_size(first_match.group("size")),
                "数量": normalize_qty(qty_match.group("qty") if qty_match else 1),
            }
        )
        index += 2
    return rows


def item_info_blocks(text: str) -> list[str]:
    lines = [clean_cell(line) for line in normalize_raw_text(text).splitlines() if clean_cell(line)]
    blocks = []
    current: list[str] | None = None
    for line in lines:
        match = ITEM_INFO_LINE_RE.match(line)
        if match:
            if current:
                blocks.append("\n".join(current))
            current = [match.group("value")]
            continue

        if current is None:
            continue
        if KEY_VALUE_LINE_RE.match(line):
            blocks.append("\n".join(current))
            current = None
            continue
        current.append(line)

    if current:
        blocks.append("\n".join(current))
    return [block for block in blocks if clean_cell(block)]


def item_total_count(text: str) -> int:
    match = ITEM_TOTAL_COUNT_RE.search(normalize_raw_text(text))
    return normalize_qty(match.group("qty") if match else 1)


def split_item_info_title(title: object, rule_config: object | None = None) -> tuple[str, str]:
    text = clean_cell(title)
    shoe, spec = split_title_shoe_and_spec(text, rule_config)

    spaced_parts = [part for part in re.split(r"\s+", text) if clean_cell(part)]
    tail_match = ITEM_INFO_SPEC_TAIL_RE.search(text)
    fallback_spec = ""
    if len(spaced_parts) > 1:
        fallback_spec = clean_item_info_spec(spaced_parts[-1])
    elif tail_match:
        fallback_spec = clean_cell(tail_match.group(0))

    if shoe:
        if fallback_spec and (not spec or len(spec) > max(12, len(fallback_spec) + 6) or fallback_spec in spec):
            spec = fallback_spec
        if not spec:
            spec = clean_spec(text)
    else:
        spec = fallback_spec or clean_item_info_spec(text)
    return clean_cell(shoe), clean_item_info_spec(spec)


def parse_item_info_groups(text: str, rule_config: object | None = None) -> list[dict]:
    rows = []
    default_qty = item_total_count(text)
    for block in item_info_blocks(text):
        for match in ITEM_INFO_ITEM_RE.finditer(block):
            title = clean_cell(match.group("title"))
            size = normalize_size(match.group("size"))
            if not title or not size:
                continue
            qty = match.group("qty_bracket") or match.group("qty_x") or match.group("qty_plain") or default_qty
            shoe, spec = split_item_info_title(title, rule_config)
            parse_status = "已解析" if shoe else "缺少鞋款规则"
            rows.append(
                {
                    "店铺名": "",
                    "店铺关键词": "",
                    "面单模式": MODE_DIRECT_SHOP_PRINT,
                    "商品简称": shoe,
                    "规格": spec,
                    "尺码": size,
                    "数量": normalize_qty(qty),
                    PARSE_STATUS_FIELD: parse_status,
                }
            )
    return rows


def parse_segment(segment: str, rule_config: object | None = None) -> dict:
    text = strip_tracking_noise(segment)
    row = parse_labeled_size(text, rule_config)
    if row is None:
        row = parse_title_quantity_segment(text, rule_config)
    if row is None:
        row = parse_spec_stuck_title_segment(text, rule_config)
    if row is None and "," in text:
        row = parse_comma_segment(text, rule_config)
    if row is None:
        row = parse_space_segment(text, rule_config)
    if row is None:
        shop, body = split_shop_name(text)
        shop_keyword = shop_hint_from_remainder(body)
        shoe, spec = split_known_prefix(body)
        row = {"店铺名": shop, "店铺关键词": shop_keyword, "面单模式": MODE_SHOP_CODE if shop else MODE_UNKNOWN, "商品简称": shoe, "规格": spec, "尺码": "", "数量": 1}
    return row


def is_complete_waybill_row(row: dict) -> bool:
    return bool(normalize_size(row.get("尺码", "")))


def output_row(parsed: dict, remark: str) -> dict:
    values = dict(parsed)
    values["备注"] = remark
    row = {field: values.get(field, "") for field in OUTPUT_FIELDS}
    if values.get(PARSE_STATUS_FIELD):
        row[PARSE_STATUS_FIELD] = values.get(PARSE_STATUS_FIELD)
    return row


def row_key(row: dict) -> tuple[str, ...]:
    return tuple(str(row.get(field, "")).strip() for field in OUTPUT_FIELDS)


def row_item_signature(row: dict) -> tuple[str, str, str, str]:
    return (
        clean_cell(row.get("规格", "")),
        clean_cell(row.get("尺码", "")),
        str(normalize_qty(row.get("数量", 1))),
        clean_cell(row.get("备注", "")),
    )


def add_output_row(rows: list[dict], seen: set, parsed: dict, remark: str) -> None:
    row = output_row(parsed, remark)
    key = row_key(row)
    if key in seen:
        return

    has_shoe = bool(clean_cell(row.get("商品简称", "")))
    signature = row_item_signature(row)
    if has_shoe:
        for old in list(rows):
            if not clean_cell(old.get("商品简称", "")) and row_item_signature(old) == signature:
                rows.remove(old)
                seen.discard(row_key(old))
    elif any(clean_cell(old.get("商品简称", "")) and row_item_signature(old) == signature for old in rows):
        return

    rows.append(row)
    seen.add(key)


def inherit_shop_context(row: dict, shop_name: str, shop_keyword: str) -> dict:
    if not shop_name or clean_cell(row.get("店铺名", "")):
        return row
    if clean_cell(row.get("面单模式", "")) not in {"", MODE_UNKNOWN}:
        return row
    item = dict(row)
    item["店铺名"] = shop_name
    if shop_keyword:
        item["店铺关键词"] = shop_keyword
    item["面单模式"] = MODE_SHOP_CODE
    return item


def parse_waybill_raw_text(raw_text: object, remark_text: object = "", rule_config: object | None = None) -> list[dict]:
    raw = normalize_raw_text(raw_text)
    if not raw:
        return []

    remark = clean_remark(remark_text)
    rows = []
    seen = set()
    context_shop = ""
    context_keyword = ""

    for parsed in parse_item_info_groups(raw, rule_config):
        if not is_complete_waybill_row(parsed):
            continue
        add_output_row(rows, seen, parsed, remark)

    for parsed in parse_labeled_item_groups(raw, rule_config):
        if not is_complete_waybill_row(parsed):
            continue
        if clean_cell(parsed.get("店铺名", "")):
            context_shop = clean_cell(parsed.get("店铺名", ""))
            context_keyword = clean_cell(parsed.get("店铺关键词", "")) or context_keyword
        add_output_row(rows, seen, parsed, remark)

    for parsed in parse_spec_size_title_pairs(raw, rule_config):
        if not is_complete_waybill_row(parsed):
            continue
        add_output_row(rows, seen, parsed, remark)

    for segment in split_glued_items(raw):
        parsed = parse_segment(segment, rule_config)
        if not is_complete_waybill_row(parsed):
            continue
        if clean_cell(parsed.get("店铺名", "")):
            context_shop = clean_cell(parsed.get("店铺名", ""))
            context_keyword = clean_cell(parsed.get("店铺关键词", "")) or context_keyword
        else:
            parsed = inherit_shop_context(parsed, context_shop, context_keyword)
        add_output_row(rows, seen, parsed, remark)
    return rows
