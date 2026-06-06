"""
SKU image binding batch tool.

This tool imports user-provided SKU/image exports into the existing
data/images and data/image_categories storage. It does not crawl Taobao,
Douyin, or bypass login/captcha systems; feed it seller exports, copied image
URLs, or downloaded image folders.
"""

from __future__ import annotations

import argparse
import mimetypes
import os
import re
import shutil
import sys
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from urllib.error import URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

SRC_ROOT = Path(__file__).resolve().parents[1]
if str(SRC_ROOT) not in sys.path:
    sys.path.insert(0, str(SRC_ROOT))

import pandas as pd

from utils.order_secure_common import (
    ImageMatcher,
    cleanup_unused_image_files,
    get_active_system,
    get_data_dir,
    get_image_category_dir,
    get_output_dir,
    image_storage_summary,
    load_data,
    load_image_category_map,
    load_image_map_for_categories,
    make_image_key,
    normalize_image_aliases,
    normalize_match_text,
    normalize_text,
    upsert_image_binding,
)


IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
DIANTOUSHI_SKU_DIR = "SKU图"
DEFAULT_TIMEOUT = 25
DEFAULT_MAX_IMAGE_MB = 20

COLUMN_ALIASES = {
    "category": [
        "鞋款",
        "商品简称",
        "分类",
        "图片分类",
        "商品分类",
        "category",
        "shoe",
        "style",
    ],
    "spec": [
        "规格",
        "SKU",
        "sku",
        "颜色分类",
        "销售规格",
        "商品规格",
        "规格名称",
        "颜色",
        "款式",
        "货号",
        "spec",
    ],
    "aliases": ["别名", "图片别名", "匹配别名", "同义词", "aliases", "alias"],
    "image_path": [
        "图片路径",
        "图片文件",
        "本地图片",
        "图片",
        "主图文件",
        "image_path",
        "image",
        "path",
        "file",
        "filename",
    ],
    "image_url": [
        "图片链接",
        "图片URL",
        "图片url",
        "主图链接",
        "主图URL",
        "image_url",
        "url",
        "main_image_url",
    ],
    "title": ["商品标题", "货品标题", "标题", "商品名称", "title", "name"],
    "remark": ["备注", "卖家备注", "商家备注", "买家留言", "留言", "remark", "note"],
    "platform": ["平台", "来源平台", "店铺平台", "platform", "source"],
    "product_id": ["商品ID", "商品id", "item_id", "product_id", "货号"],
}

TEMPLATE_COLUMNS = [
    "鞋款",
    "规格",
    "图片路径",
    "图片链接",
    "别名",
    "来源平台",
    "商品ID",
    "商品标题",
    "备注",
]


@dataclass
class ImportRow:
    row_no: int
    category: str
    spec: str
    aliases: list[str]
    image_path: str
    image_url: str
    title: str
    platform: str
    product_id: str


@dataclass
class ImageSource:
    kind: str
    path: Path | None = None
    url: str = ""
    raw: bytes | None = None
    filename: str = ""
    message: str = ""


def now_tag() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def output_path(prefix: str, suffix: str = ".xlsx") -> Path:
    return Path(get_output_dir()) / f"{prefix}_{now_tag()}{suffix}"


def header_key(value: object) -> str:
    return normalize_match_text(value).casefold()


def clean_cell(value: object) -> str:
    if value is None:
        return ""
    text = "" if pd.isna(value) else str(value)
    return normalize_text(text)


def looks_like_url(value: str) -> bool:
    parsed = urlparse(str(value or "").strip())
    return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)


def read_table(path: Path) -> pd.DataFrame:
    suffix = path.suffix.lower()
    if suffix in {".xlsx", ".xlsm", ".xls"}:
        df = pd.read_excel(path, dtype=str)
    elif suffix == ".csv":
        last_error: Exception | None = None
        for encoding in ("utf-8-sig", "utf-8", "gbk"):
            try:
                df = pd.read_csv(path, dtype=str, encoding=encoding)
                break
            except UnicodeDecodeError as exc:
                last_error = exc
        else:
            raise last_error or ValueError("CSV 编码无法识别")
    else:
        raise ValueError("只支持 .xlsx/.xls/.csv 表格")

    df = df.fillna("")
    df.columns = [str(col).strip() for col in df.columns]
    return df


def resolve_column(df: pd.DataFrame, override: str, logical_name: str) -> str:
    if override:
        if override not in df.columns:
            raise ValueError(f"找不到指定列：{override}")
        return override

    available = {header_key(col): col for col in df.columns}
    for alias in COLUMN_ALIASES.get(logical_name, []):
        found = available.get(header_key(alias))
        if found:
            return found
    return ""


def table_columns(df: pd.DataFrame, args: argparse.Namespace) -> dict[str, str]:
    return {
        name: resolve_column(df, getattr(args, f"{name}_col", ""), name)
        for name in COLUMN_ALIASES
    }


def row_value(row: pd.Series, column: str) -> str:
    return clean_cell(row.get(column, "")) if column else ""


def extract_import_rows(df: pd.DataFrame, args: argparse.Namespace) -> list[ImportRow]:
    columns = table_columns(df, args)
    default_category = normalize_text(getattr(args, "default_category", ""))
    rows: list[ImportRow] = []

    for index, row in df.iterrows():
        category = row_value(row, columns["category"]) or default_category
        spec = row_value(row, columns["spec"])
        aliases = normalize_image_aliases(row_value(row, columns["aliases"]))
        title = row_value(row, columns["title"])
        product_id = row_value(row, columns["product_id"])
        if product_id and product_id not in aliases:
            aliases.append(product_id)
        if title and title not in aliases:
            aliases.append(title)

        rows.append(
            ImportRow(
                row_no=int(index) + 2,
                category=category,
                spec=spec,
                aliases=[alias for alias in aliases if alias and alias != spec],
                image_path=row_value(row, columns["image_path"]),
                image_url=row_value(row, columns["image_url"]),
                title=title,
                platform=row_value(row, columns["platform"]),
                product_id=product_id,
            )
        )
    return rows


def iter_image_files(image_dir: Path | None) -> list[Path]:
    if not image_dir or not image_dir.exists():
        return []
    return sorted(
        path
        for path in image_dir.rglob("*")
        if path.is_file() and path.suffix.lower() in IMAGE_EXTS
    )


def image_marker(path: Path) -> str:
    return header_key(path.stem)


def best_named_image(
    image_files: list[Path],
    category: str,
    spec: str,
    title: str = "",
) -> tuple[Path | None, str]:
    spec_marker = header_key(spec)
    category_marker = header_key(category)
    title_marker = header_key(title)
    if not spec_marker:
        return None, ""

    best: tuple[int, Path | None] = (0, None)
    matches_with_same_score = 0

    for path in image_files:
        marker = image_marker(path)
        if not marker:
            continue

        score = 0
        if marker in {spec_marker, f"{category_marker}{spec_marker}"}:
            score = 110
        elif spec_marker in marker:
            score = 72
        elif marker in spec_marker and len(marker) >= 4:
            score = 66

        if score and category_marker and category_marker in marker:
            score += 30
        if score and title_marker and len(title_marker) >= 4 and title_marker in marker:
            score += 8

        if score > best[0]:
            best = (score, path)
            matches_with_same_score = 1
        elif score == best[0] and score > 0:
            matches_with_same_score += 1

    if best[0] >= 100 or (best[0] >= 72 and matches_with_same_score == 1):
        return best[1], f"文件名自动匹配，分数 {best[0]}"
    return None, ""


def resolve_local_path(value: str, table_path: Path, image_dir: Path | None) -> Path | None:
    if not value or looks_like_url(value):
        return None

    raw = value.strip().strip('"').strip("'")
    candidates = [Path(raw)]
    if not Path(raw).is_absolute():
        candidates.append(table_path.parent / raw)
        if image_dir:
            candidates.append(image_dir / raw)
            candidates.append(image_dir / Path(raw).name)

    for candidate in candidates:
        try:
            resolved = candidate.expanduser().resolve()
        except OSError:
            continue
        if resolved.exists() and resolved.is_file() and resolved.suffix.lower() in IMAGE_EXTS:
            return resolved
    return None


def filename_from_url(url: str, content_type: str = "") -> str:
    path_name = unquote(Path(urlparse(url).path).name)
    if Path(path_name).suffix.lower() in IMAGE_EXTS:
        return path_name
    ext = mimetypes.guess_extension(content_type.split(";")[0].strip()) if content_type else ""
    if ext not in IMAGE_EXTS:
        ext = ".jpg"
    return f"downloaded{ext}"


def download_image(url: str, timeout: int, max_bytes: int) -> ImageSource:
    request = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 SKUImageBinder/1.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            raw = response.read(max_bytes + 1)
            if len(raw) > max_bytes:
                return ImageSource(kind="error", url=url, message="图片超过大小限制")
            content_type = response.headers.get("Content-Type", "")
    except (OSError, URLError) as exc:
        return ImageSource(kind="error", url=url, message=f"下载失败：{exc}")

    return ImageSource(
        kind="url",
        url=url,
        raw=raw,
        filename=filename_from_url(url, content_type),
        message="URL下载",
    )


def resolve_image_source(
    item: ImportRow,
    table_path: Path,
    image_dir: Path | None,
    image_files: list[Path],
    args: argparse.Namespace,
) -> ImageSource:
    if looks_like_url(item.image_path):
        url = item.image_path
    else:
        local = resolve_local_path(item.image_path, table_path, image_dir)
        if local:
            return ImageSource(kind="file", path=local, filename=local.name, message="表格图片路径")
        url = item.image_url

    if url and looks_like_url(url):
        if args.no_download:
            return ImageSource(kind="error", url=url, message="已禁用URL下载")
        return download_image(
            url,
            timeout=args.timeout,
            max_bytes=args.max_image_mb * 1024 * 1024,
        )

    auto, reason = best_named_image(image_files, item.category, item.spec, item.title)
    if auto:
        return ImageSource(kind="file", path=auto, filename=auto.name, message=reason)
    return ImageSource(kind="error", message="未找到图片文件或图片链接")


def backup_image_category_files() -> Path:
    src = Path(get_image_category_dir())
    dst = Path(get_data_dir()) / "backup" / f"image_categories_{now_tag()}"
    dst.parent.mkdir(parents=True, exist_ok=True)
    if src.exists():
        shutil.copytree(src, dst)
    else:
        dst.mkdir(parents=True, exist_ok=True)
    return dst


def write_report(records: list[dict], path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    df = pd.DataFrame(records)
    if path.suffix.lower() == ".csv":
        df.to_csv(path, index=False, encoding="utf-8-sig")
    else:
        df.to_excel(path, index=False)
    return path


def clean_diantoushi_sku_spec(name: str) -> str:
    stem = Path(str(name or "")).stem
    stem = stem.replace("ＳＫＵ图", "SKU图")
    stem = stem.replace("sku图", "SKU图")
    stem = stem.replace("SKU圖", "SKU图")
    stem = normalize_text(stem).strip("_- ")
    # 店透视文件名通常是：SKU图_01_PAF联名米色.png
    stem = re.sub(r"^SKU图[_\-\s]*\d+[_\-\s]*", "", stem, flags=re.I)
    stem = re.sub(r"^SKU[_\-\s]*\d+[_\-\s]*", "", stem, flags=re.I)
    return normalize_text(stem)


def is_diantoushi_sku_member(name: str) -> bool:
    normalized = str(name or "").replace("\\", "/")
    filename = Path(normalized).name
    if Path(filename).suffix.lower() not in IMAGE_EXTS:
        return False
    return f"/{DIANTOUSHI_SKU_DIR}/" in f"/{normalized}" or filename.startswith("SKU图_")


def import_diantoushi_zip(args: argparse.Namespace) -> tuple[dict, Path]:
    zip_path = Path(args.input).resolve()
    category = normalize_text(getattr(args, "category", "") or getattr(args, "default_category", ""))
    if not category:
        raise ValueError("请先定义鞋款名称")
    if not zip_path.exists() or zip_path.suffix.lower() != ".zip":
        raise ValueError("请选择店透视下载出来的 .zip 文件")

    report: list[dict] = []
    backup_path = ""
    if not args.dry_run and not getattr(args, "no_backup", False):
        backup_path = str(backup_image_category_files())

    counters = {
        "total": 0,
        "imported": 0,
        "overwritten": 0,
        "would_import": 0,
        "skipped": 0,
        "failed": 0,
        "backup": backup_path,
        "deleted_images": 0,
    }

    with zipfile.ZipFile(zip_path) as archive:
        members = [item for item in archive.infolist() if not item.is_dir() and is_diantoushi_sku_member(item.filename)]
        members.sort(key=lambda item: item.filename)
        counters["total"] = len(members)
        for index, member in enumerate(members, 1):
            filename = Path(member.filename.replace("\\", "/")).name
            spec = clean_diantoushi_sku_spec(filename)
            record = {
                "行号": index,
                "状态": "",
                "鞋款": category,
                "规格": spec,
                "别名": "",
                "图片来源": "店透视ZIP",
                "图片文件": filename,
                "说明": member.filename,
            }
            if not spec:
                record["状态"] = "跳过"
                record["说明"] = f"无法从文件名识别规格：{member.filename}"
                counters["skipped"] += 1
                report.append(record)
                continue

            if args.dry_run:
                record["状态"] = "预览"
                counters["would_import"] += 1
                report.append(record)
                continue

            try:
                existing = make_image_key(category, spec) in load_image_category_map(category)
                saved = upsert_image_binding(
                    category,
                    spec,
                    image_bytes=archive.read(member),
                    filename=filename,
                    aliases=[],
                )
                record["状态"] = "已覆盖" if existing else "已导入"
                record["图片文件"] = saved.get("image_file", filename)
                counters["imported"] += 1
                if existing:
                    counters["overwritten"] += 1
            except Exception as exc:
                record["状态"] = "失败"
                record["说明"] = f"写入失败：{exc}"
                counters["failed"] += 1
            report.append(record)

    if counters["total"] <= 0:
        raise ValueError("ZIP 里没有找到 SKU图 文件夹或 SKU图_ 开头的图片")

    if not args.dry_run and counters["imported"] > 0:
        cleanup = cleanup_unused_image_files()
        counters["deleted_images"] = cleanup.get("deleted", 0)
        counters["freed_bytes"] = cleanup.get("freed_bytes", 0)

    report_path = Path(args.report).resolve() if getattr(args, "report", "") else output_path("店透视SKU图片导入报告")
    write_report(report, report_path)
    return counters, report_path


def create_template(args: argparse.Namespace) -> Path:
    out = Path(args.out).resolve() if args.out else output_path("SKU图片绑定模板")
    sample = {
        "鞋款": "昂跑",
        "规格": "Cloudtilt白黑",
        "图片路径": r"D:\店铺图片\昂跑_Cloudtilt白黑.jpg",
        "图片链接": "",
        "别名": "白黑Cloudtilt；Cloudtilt 黑白",
        "来源平台": "淘宝/抖音",
        "商品ID": "",
        "商品标题": "",
        "备注": "图片路径和图片链接二选一；有本地图片优先用本地图片。",
    }
    write_report([sample], out)
    return out


def import_bindings(args: argparse.Namespace) -> tuple[dict, Path]:
    table_path = Path(args.input).resolve()
    image_dir = Path(args.image_dir).resolve() if args.image_dir else None
    df = read_table(table_path)
    rows = extract_import_rows(df, args)
    image_files = iter_image_files(image_dir)
    report: list[dict] = []

    backup_path = ""
    if not args.dry_run and not args.no_backup:
        backup_path = str(backup_image_category_files())

    counters = {
        "total": len(rows),
        "imported": 0,
        "overwritten": 0,
        "would_import": 0,
        "skipped": 0,
        "failed": 0,
        "backup": backup_path,
        "deleted_images": 0,
    }

    for item in rows:
        record = {
            "行号": item.row_no,
            "状态": "",
            "鞋款": item.category,
            "规格": item.spec,
            "别名": "；".join(item.aliases),
            "图片来源": "",
            "图片文件": "",
            "说明": "",
        }

        if not item.category or not item.spec:
            record["状态"] = "跳过"
            record["说明"] = "缺少鞋款或规格"
            counters["skipped"] += 1
            report.append(record)
            continue

        source = resolve_image_source(item, table_path, image_dir, image_files, args)
        record["图片来源"] = source.kind
        record["图片文件"] = str(source.path or source.url or source.filename or "")
        record["说明"] = source.message

        if source.kind == "error":
            record["状态"] = "失败"
            counters["failed"] += 1
            report.append(record)
            continue

        if args.dry_run:
            record["状态"] = "预览"
            counters["would_import"] += 1
            report.append(record)
            continue

        try:
            existing = make_image_key(item.category, item.spec) in load_image_category_map(item.category)
            if source.kind == "url":
                saved = upsert_image_binding(
                    item.category,
                    item.spec,
                    image_bytes=source.raw,
                    filename=source.filename,
                    aliases=item.aliases,
                )
            else:
                saved = upsert_image_binding(
                    item.category,
                    item.spec,
                    source_path=str(source.path),
                    aliases=item.aliases,
                )
            record["状态"] = "已覆盖" if existing else "已导入"
            record["图片文件"] = saved.get("image_file", record["图片文件"])
            counters["imported"] += 1
            if existing:
                counters["overwritten"] += 1
        except Exception as exc:
            record["状态"] = "失败"
            record["说明"] = f"写入失败：{exc}"
            counters["failed"] += 1
        report.append(record)

    if not args.dry_run and counters["imported"] > 0:
        cleanup = cleanup_unused_image_files()
        counters["deleted_images"] = cleanup.get("deleted", 0)
        counters["freed_bytes"] = cleanup.get("freed_bytes", 0)

    report_path = Path(args.report).resolve() if args.report else output_path("SKU图片批量导入报告")
    write_report(report, report_path)
    return counters, report_path


def extract_missing_candidates(
    df: pd.DataFrame,
    args: argparse.Namespace,
) -> list[dict[str, str]]:
    columns = table_columns(df, args)
    default_category = normalize_text(getattr(args, "default_category", ""))
    rows: list[dict[str, str]] = []
    for _, row in df.iterrows():
        category = row_value(row, columns["category"]) or default_category
        spec = row_value(row, columns["spec"])
        title = row_value(row, columns["title"])
        remark = row_value(row, columns["remark"])
        if category and spec:
            rows.append({
                "category": category,
                "spec": spec,
                "title": title,
                "remark": remark,
            })
    return rows


def missing_report(args: argparse.Namespace) -> tuple[dict, Path]:
    candidates: list[dict[str, str]] = []
    for file in args.inputs:
        path = Path(file).resolve()
        df = read_table(path)
        candidates.extend(extract_missing_candidates(df, args))

    categories = sorted({item["category"] for item in candidates})
    data = load_data()
    system, _ = get_active_system(data)
    image_map = load_image_map_for_categories(system, categories)
    matcher = ImageMatcher(image_map)

    missing: dict[tuple[str, str], dict] = {}
    matched = 0
    for item in candidates:
        found = matcher.find(
            item["category"],
            item["spec"],
            item.get("remark", ""),
            item.get("title", ""),
        )
        if found:
            matched += 1
            continue
        key = (item["category"], item["spec"])
        bucket = missing.setdefault(
            key,
            {
                "鞋款": item["category"],
                "规格": item["spec"],
                "出现次数": 0,
                "示例标题": item.get("title", ""),
                "示例备注": item.get("remark", ""),
            },
        )
        bucket["出现次数"] += 1
        if not bucket["示例标题"] and item.get("title"):
            bucket["示例标题"] = item["title"]
        if not bucket["示例备注"] and item.get("remark"):
            bucket["示例备注"] = item["remark"]

    records = sorted(
        missing.values(),
        key=lambda item: (-int(item["出现次数"]), item["鞋款"], item["规格"]),
    )
    report_path = Path(args.report).resolve() if args.report else output_path("缺图SKU清单")
    write_report(records, report_path)
    return {
        "total_rows": len(candidates),
        "matched_rows": matched,
        "missing_unique": len(records),
    }, report_path


def print_import_summary(counters: dict, report_path: Path) -> None:
    stats = image_storage_summary(count_entries=True)
    print(f"总行数：{counters['total']}")
    if counters.get("would_import"):
        print(f"可导入：{counters['would_import']}")
    print(f"已导入：{counters['imported']}")
    print(f"已覆盖：{counters.get('overwritten', 0)}")
    print(f"跳过：{counters['skipped']}")
    print(f"失败：{counters['failed']}")
    print(f"清理无关系图片：{counters.get('deleted_images', 0)}")
    if counters.get("backup"):
        print(f"索引备份：{counters['backup']}")
    print(f"报告：{report_path}")
    print(
        "图片库："
        f"{stats.get('entries') or 0} 条绑定 / "
        f"{stats.get('category_files') or 0} 个分类文件 / "
        f"{stats.get('image_files') or 0} 个图片文件"
    )


def add_column_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--category-col", default="", help="鞋款/分类列名")
    parser.add_argument("--spec-col", default="", help="规格/SKU列名")
    parser.add_argument("--aliases-col", default="", help="别名列名")
    parser.add_argument("--image-path-col", default="", help="本地图片路径列名")
    parser.add_argument("--image-url-col", default="", help="图片链接列名")
    parser.add_argument("--title-col", default="", help="商品标题列名")
    parser.add_argument("--remark-col", default="", help="备注列名")
    parser.add_argument("--platform-col", default="", help="平台列名")
    parser.add_argument("--product-id-col", default="", help="商品ID/货号列名")
    parser.add_argument("--default-category", default="", help="表格没有鞋款列时使用的默认鞋款")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="批量导入 SKU 图片绑定，或生成缺图 SKU 清单。"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    template = sub.add_parser("template", help="生成 SKU 图片绑定表模板")
    template.add_argument("--out", default="", help="模板输出路径，默认写入 output")

    importer = sub.add_parser("import", help="从 Excel/CSV 批量导入图片绑定")
    importer.add_argument("input", help="SKU 图片绑定 Excel/CSV")
    importer.add_argument("--image-dir", default="", help="本地图片目录；表格只写文件名时会在这里查找")
    importer.add_argument("--report", default="", help="导入报告输出路径")
    importer.add_argument("--dry-run", action="store_true", help="只生成预览报告，不写入图片库")
    importer.add_argument("--no-backup", action="store_true", help="导入前不备份 image_categories")
    importer.add_argument("--no-download", action="store_true", help="不下载表格中的图片 URL")
    importer.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="URL 下载超时时间")
    importer.add_argument("--max-image-mb", type=int, default=DEFAULT_MAX_IMAGE_MB, help="单张图片最大 MB")
    add_column_args(importer)

    diantoushi = sub.add_parser("diantoushi-zip", help="从店透视全部图片 ZIP 直接导入 SKU 图片关系")
    diantoushi.add_argument("input", help="店透视下载出来的 .zip 文件")
    diantoushi.add_argument("--category", "--shoe", default="", help="要写入系统的鞋款名称")
    diantoushi.add_argument("--report", default="", help="导入报告输出路径")
    diantoushi.add_argument("--dry-run", action="store_true", help="只预览，不写入图片库")
    diantoushi.add_argument("--no-backup", action="store_true", help="导入前不备份 image_categories")

    missing = sub.add_parser("missing", help="从订单/面单识别 Excel 生成缺图清单")
    missing.add_argument("inputs", nargs="+", help="订单、面单识别或五字段 Excel/CSV")
    missing.add_argument("--report", default="", help="缺图报告输出路径")
    add_column_args(missing)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "template":
            path = create_template(args)
            print(f"模板已生成：{path}")
        elif args.command == "import":
            counters, report_path = import_bindings(args)
            print_import_summary(counters, report_path)
        elif args.command == "diantoushi-zip":
            counters, report_path = import_diantoushi_zip(args)
            print_import_summary(counters, report_path)
        elif args.command == "missing":
            summary, report_path = missing_report(args)
            print(f"检查行数：{summary['total_rows']}")
            print(f"已匹配行数：{summary['matched_rows']}")
            print(f"缺图SKU数：{summary['missing_unique']}")
            print(f"报告：{report_path}")
        return 0
    except Exception as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
