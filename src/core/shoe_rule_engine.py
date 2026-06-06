# -*- coding: utf-8 -*-
from __future__ import annotations

import re
from typing import Any


SHOP_CODE_PREFIXES = ("秒", "范")


def normalize_rule_text(value: Any) -> str:
    return str(value or "").strip().replace(" ", "").replace("\u3000", "")


def _match_text(value: Any) -> str:
    return normalize_rule_text(value).casefold()


def _canonical_keyword(value: Any) -> str:
    text = normalize_rule_text(value)
    if re.fullmatch(r"[A-Za-z0-9._-]+", text):
        return text.upper()
    return text


def make_match_context(
    short_name: Any = "",
    title: Any = "",
    raw_spec: Any = "",
    remark: Any = "",
    size: Any = "",
    qty: Any = "",
) -> dict[str, str]:
    return {
        "short_raw": str(short_name or ""),
        "title_raw": str(title or ""),
        "spec_raw": str(raw_spec or ""),
        "remark_raw": str(remark or ""),
        "size_raw": str(size or ""),
        "qty_raw": str(qty or ""),
        "short": _match_text(short_name),
        "title": _match_text(title),
        "spec": _match_text(raw_spec),
        "remark": _match_text(remark),
        "size": _match_text(size),
        "qty": _match_text(qty),
    }


def _rule_field(rule: dict[str, Any]) -> str:
    return str(rule.get("field") or "全部").strip()


def score_rule(rule: dict[str, Any], context: dict[str, str]) -> int:
    keyword = _match_text(rule.get("keyword", ""))
    if not keyword:
        return -1
    field = _rule_field(rule)
    kw_len = len(keyword)

    if field in {"鞋款", "商品简称", "鞋款简称"}:
        if keyword in context["short"]:
            return 1000 + kw_len
        return -1
    if field in {"规格", "销售规格"}:
        if keyword in context["spec"]:
            return 700 + kw_len
        return -1
    if field == "备注":
        return 850 + kw_len if keyword in context["remark"] else -1
    if field == "尺码":
        return 650 + kw_len if keyword in context["size"] else -1
    if field == "数量":
        return 600 + kw_len if keyword in context["qty"] else -1
    if field in {"货品标题", "原始打印信息"}:
        return 500 + kw_len if keyword in context["title"] else -1
    if field == "全部五字段":
        for key, base in (
            ("short", 1000),
            ("remark", 850),
            ("spec", 700),
            ("size", 650),
            ("qty", 600),
        ):
            if keyword in context[key]:
                return base + kw_len
        return -1

    for key, base in (
        ("short", 1000),
        ("remark", 850),
        ("spec", 700),
        ("size", 650),
        ("qty", 600),
    ):
        if keyword in context[key]:
            return base + kw_len
    return -1


def best_rule_match(
    rules: list[dict[str, Any]],
    context: dict[str, str],
    category: Any = "",
) -> tuple[dict[str, Any] | None, int]:
    wanted_category = normalize_rule_text(category)
    best_rule = None
    best_score = -1
    for rule in rules or []:
        if not isinstance(rule, dict):
            continue
        if wanted_category and normalize_rule_text(rule.get("category", "")) != wanted_category:
            continue
        score = score_rule(rule, context)
        if score > best_score:
            best_rule = rule
            best_score = score
    return best_rule, best_score


def configured_output_shoe(rule: dict[str, Any]) -> str:
    for key in ("output_shoe", "shoe_name", "style_name", "识别鞋款", "输出鞋款"):
        value = normalize_rule_text(rule.get(key, ""))
        if value:
            return value
    return ""


def infer_output_shoe(rule: dict[str, Any], context: dict[str, str]) -> str:
    output = configured_output_shoe(rule)
    if output:
        return output

    keyword = normalize_rule_text(rule.get("keyword", ""))
    if not keyword:
        return ""

    compact_keyword = normalize_rule_text(keyword)
    if re.fullmatch(r"\d+(?:\.\d+)?", compact_keyword):
        return compact_keyword

    short = normalize_rule_text(context.get("short_raw", ""))
    if re.match(r"^(?:秒|范)\d+", compact_keyword, flags=re.I):
        if short.casefold().startswith(compact_keyword.casefold()) and len(short) > len(compact_keyword):
            suffix = short[len(compact_keyword):].strip("-_/|,，;；")
            if suffix and len(suffix) <= 24:
                return _canonical_keyword(suffix)
        return ""

    if re.search(r"[A-Za-z]", compact_keyword) or re.fullmatch(r"\d+(?:\.\d+)?", compact_keyword):
        return _canonical_keyword(compact_keyword)
    return compact_keyword


def detect_category_from_rules(
    rules: list[dict[str, Any]],
    short_name: Any = "",
    title: Any = "",
    raw_spec: Any = "",
    remark: Any = "",
    size: Any = "",
    qty: Any = "",
) -> str:
    context = make_match_context(short_name, title, raw_spec, remark, size, qty)
    rule, score = best_rule_match(rules, context)
    if not rule or score < 0:
        return "未分类"
    return normalize_rule_text(rule.get("category", "")) or "未分类"


def detect_output_shoe_from_rules(
    rules: list[dict[str, Any]],
    short_name: Any = "",
    title: Any = "",
    raw_spec: Any = "",
    remark: Any = "",
    size: Any = "",
    qty: Any = "",
    category: Any = "",
) -> str:
    context = make_match_context(short_name, title, raw_spec, remark, size, qty)
    rule, score = best_rule_match(rules, context, category=category)
    if not rule or score < 0:
        return ""
    return infer_output_shoe(rule, context)
