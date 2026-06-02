# -*- coding: utf-8 -*-
from __future__ import annotations

import re


APP_VERSION = "V7.8.8_20260602"
APP_EDITION = "面单监听任务ID保留版"
APP_NAME = "订单整理管理系统"


def version_parts(version: str = APP_VERSION) -> tuple[str, str]:
    match = re.match(r"^V?(?P<number>\d+(?:\.\d+)*)(?:_(?P<date>\d{8}))?", version.strip(), flags=re.I)
    if not match:
        return version, ""
    return match.group("number"), match.group("date") or ""


def display_version(version: str = APP_VERSION) -> str:
    number, date = version_parts(version)
    return f"{number} / {date}" if date else number


def build_slug(version: str = APP_VERSION) -> str:
    number, _ = version_parts(version)
    return "v" + "_".join(re.findall(r"\d+", number))


def window_title(app_name: str) -> str:
    return f"{app_name} - {APP_VERSION}"
