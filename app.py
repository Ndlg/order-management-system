def normalize_qty(value):
    try:
        if value is None or str(value).strip() == "":
            return 1
        return int(float(value))
    except Exception:
        return 1


def size_sort_key(size):
    s = str(size).strip()
    try:
        return (0, float(s))
    except Exception:
        return (1, s)


def merge_sizes(values):
    """
    旧兼容函数：仅合并尺码列表。
    """
    vals = [str(v).strip() for v in values if str(v).strip()]
    unique = []
    for v in vals:
        if v not in unique:
            unique.append(v)
    return " ".join(sorted(unique, key=size_sort_key))


def merge_size_quantity(group):
    """
    按商品数量展开尺码。
    例如：41码，数量3，输出为：41 41 41。
    """
    expanded = []

    for _, row in group.iterrows():
        size = str(row.get("尺码", "")).strip()
        if not size:
            continue

        qty = normalize_qty(row.get("数量", 1))
        for _ in range(max(qty, 0)):
            expanded.append(size)

    return " ".join(sorted(expanded, key=size_sort_key))


import os
import re
import uuid
import secrets
import inspect
import importlib
import traceback
import zipfile
from datetime import datetime
from typing import List

import pandas as pd
from PIL import Image as PILImage
from fastapi import FastAPI, UploadFile, File, Form
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from openpyxl import load_workbook
from openpyxl.drawing.image import Image as XLImage
from openpyxl.styles import Alignment, Font, PatternFill, Border, Side

from order_core import generate_order_file
from order_secure_common import (
    load_data, save_data, get_output_dir, get_temp_dir, get_data_dir, normalize_text,
    get_data_file, make_image_key, base64_to_image_file, safe_filename, col_letter_to_index, ImageMatcher, load_image_map_for_categories,
    image_storage_summary,
)

app = FastAPI(title="订单整理系统 Web服务")

WEB_VERSION = "V7.5.1-LiteData-20260525"
ALLOWED_OUTPUT_MODES = {"合并一个Sheet", "按档口分Sheet", "按档口分文档"}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_DIR = os.path.join(BASE_DIR, "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
DATA_CACHE = {"signature": None, "data": None}

def debug_environment():
    info = {"web_version": WEB_VERSION, "app_file": __file__, "base_dir": BASE_DIR}
    try:
        import order_core
        info["order_core_file"] = getattr(order_core, "__file__", "")
        info["order_core_has_ImageMatcher_name"] = "ImageMatcher" in dir(order_core)
        info["order_core_has_generate_order_file"] = hasattr(order_core, "generate_order_file")
        info["order_core_has_merge_size_quantity"] = hasattr(order_core, "merge_size_quantity")
    except Exception:
        info["order_core_import_error"] = traceback.format_exc()
    try:
        import order_secure_common
        info["order_secure_common_file"] = getattr(order_secure_common, "__file__", "")
        info["secure_common_has_ImageMatcher"] = hasattr(order_secure_common, "ImageMatcher")
        info["secure_common_has_get_data_dir"] = hasattr(order_secure_common, "get_data_dir")
    except Exception:
        info["order_secure_common_import_error"] = traceback.format_exc()
    try:
        from order_secure_common import ImageMatcher as _ImageMatcher
        info["direct_import_ImageMatcher"] = True
    except Exception:
        info["direct_import_ImageMatcher"] = False
        info["direct_import_ImageMatcher_error"] = traceback.format_exc()
    try:
        from order_core import generate_order_file as _generate_order_file
        info["direct_import_generate_order_file"] = True
    except Exception:
        info["direct_import_generate_order_file"] = False
        info["direct_import_generate_order_file_error"] = traceback.format_exc()
    return info



def load_html(name):
    with open(os.path.join(BASE_DIR, "templates", name), "r", encoding="utf-8") as f:
        return f.read()


def get_data_signature():
    path = get_data_file()
    if not os.path.exists(path):
        return None
    stat = os.stat(path)
    return (stat.st_mtime_ns, stat.st_size)


def load_runtime_data():
    signature = get_data_signature()
    if DATA_CACHE["data"] is not None and DATA_CACHE["signature"] == signature:
        return DATA_CACHE["data"]

    data = load_data(auto_save_on_read=False)
    DATA_CACHE["signature"] = get_data_signature()
    DATA_CACHE["data"] = data
    return data


def is_path_under(path, root):
    try:
        path_abs = os.path.abspath(path)
        root_abs = os.path.abspath(root)
        return os.path.commonpath([path_abs, root_abs]) == root_abs
    except Exception:
        return False


def zip_output_folder(folder_path):
    folder_path = os.path.abspath(folder_path)
    if not is_path_under(folder_path, get_output_dir()) or not os.path.isdir(folder_path):
        raise ValueError("只能打包输出目录内的文件夹")

    zip_path = folder_path.rstrip("\\/") + ".zip"
    if os.path.exists(zip_path):
        os.remove(zip_path)

    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for root, _, files in os.walk(folder_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                arcname = os.path.relpath(file_path, os.path.dirname(folder_path))
                zf.write(file_path, arcname)

    return zip_path


def get_current_system():
    data = load_runtime_data()

    # 新版多系统结构
    if isinstance(data, dict) and "systems" in data:
        system_id = data.get("active_system", "default")
        systems = data.get("systems", {})

        if system_id not in systems and systems:
            system_id = next(iter(systems.keys()))

        system = systems.get(system_id, {})
        return system, system_id

    # 旧版单系统结构
    return data, "default"


IMAGE_WIDTH_PX = 140
IMAGE_HEIGHT_PX = 120


@app.get("/", response_class=HTMLResponse)
def index():
    return load_html("index.html")





@app.get("/api/version")
def api_version():
    return {"ok": True, "web_version": WEB_VERSION}


@app.get("/api/self-check")
def api_self_check():
    info = debug_environment()
    info["ok"] = (
        info.get("secure_common_has_ImageMatcher") is True
        and info.get("direct_import_ImageMatcher") is True
        and info.get("direct_import_generate_order_file") is True
        and info.get("order_core_has_generate_order_file") is True
    )
    return info


@app.get("/api/debug/core-check")
def api_debug_core_check():
    try:
        from order_secure_common import ImageMatcher as _ImageMatcher
        from order_core import generate_order_file as _generate_order_file
        return {"ok": True, "web_version": WEB_VERSION, "message": "核心模块导入正常", "debug": debug_environment()}
    except Exception:
        return JSONResponse({"ok": False, "web_version": WEB_VERSION, "error": "核心模块导入失败", "traceback": traceback.format_exc(), "debug": debug_environment()}, status_code=500)


@app.get("/api/status")
def status():
    system, system_id = get_current_system()
    image_stats = image_storage_summary(count_entries=True)

    return {
        "ok": True,
        "web_version": WEB_VERSION,
        "system_id": system_id,
        "system_name": system.get("name", system_id),
        "active_template": system.get("active_template", ""),
        "category_rules": len(system.get("category_rules", [])),
        "stall_rules": len(system.get("stall_map", {})),
        "image_rules": image_stats.get("entries", 0) or 0,
        "image_category_files": image_stats.get("category_files", 0),
        "image_storage_mb": round((image_stats.get("bytes", 0) or 0) / 1024 / 1024, 2),
    }



@app.get("/api/templates")
def api_templates():
    system, system_id = get_current_system()
    templates = system.get("import_templates", [])
    active_template = system.get("active_template", "")

    return {
        "ok": True,
        "active_template": active_template,
        "templates": [
            {
                "name": t.get("name", ""),
                "mode": t.get("mode", "")
            }
            for t in templates
            if t.get("name", "")
        ]
    }


def split_items(value, sep):
    if value is None:
        return []
    return [x.strip() for x in str(value).split(sep) if str(x).strip()]


def split_spec_to_color_size(spec, split_char):
    spec = str(spec).strip()
    for sp in [split_char, "，", ",", " "]:
        if sp and sp in spec:
            parts = spec.rsplit(sp, 1)
            if len(parts) == 2:
                return parts[0].strip(), parts[1].strip()
    return spec, "未知"


def read_by_template(file_path, template):
    df = pd.read_excel(file_path)
    mode = template.get("mode", "表头")
    item_sep = template.get("item_sep", ";") or ";"
    spec_split = template.get("spec_split", "，") or "，"
    rows = []

    if mode == "表头":
        short_col = template.get("short_name", "")
        spec_col = template.get("spec", "")
        qty_col = template.get("qty", "")

        if not {short_col, spec_col, qty_col}.issubset(set(df.columns)):
            raise ValueError(f"文件缺少模板指定表头：{os.path.basename(file_path)}")

        temp = df[[short_col, spec_col, qty_col]].copy()
        temp = temp.dropna(subset=[short_col, spec_col])

        for _, row in temp.iterrows():
            names = split_items(row[short_col], item_sep)
            specs = split_items(row[spec_col], item_sep)
            qtys = split_items(row[qty_col], item_sep)
            max_len = max(len(names), len(specs), len(qtys), 1)

            for i in range(max_len):
                name = names[i] if i < len(names) else (names[-1] if names else "")
                spec = specs[i] if i < len(specs) else (specs[-1] if specs else "")
                qty = qtys[i] if i < len(qtys) else (qtys[-1] if qtys else "1")
                color, size = split_spec_to_color_size(spec, spec_split)
                title = f"{name} 颜色: {color} 尺码: {size}"
                rows.append({
                    "商品简称": name,
                    "货品标题": title,
                    "数量": qty,
                    "来源文件": os.path.basename(file_path)
                })
    else:
        title_idx = col_letter_to_index(template.get("title_col", "S"))
        qty_idx = col_letter_to_index(template.get("qty_col", "V"))

        if df.shape[1] <= max(title_idx, qty_idx):
            raise ValueError(f"文件列数不足：{os.path.basename(file_path)}")

        temp = df.iloc[:, [title_idx, qty_idx]].copy()
        temp.columns = ["货品标题", "数量"]
        temp = temp.dropna(subset=["货品标题"])

        def guess_short_name(title):
            m = re.search(r"^(.*?)\s*颜色[:：]", str(title))
            return m.group(1).strip() if m else str(title).strip()

        for _, row in temp.iterrows():
            rows.append({
                "商品简称": guess_short_name(row["货品标题"]),
                "货品标题": row["货品标题"],
                "数量": row["数量"],
                "来源文件": os.path.basename(file_path)
            })

    out = pd.DataFrame(rows)
    out["数量"] = pd.to_numeric(out["数量"], errors="coerce").fillna(1).astype(int)
    return out


def extract_size(title):
    m = re.search(r"尺码[:：]\s*([0-9.]+)", str(title))
    return m.group(1) if m else "未知"


def extract_raw_spec(title):
    m = re.search(r"颜色[:：]\s*(.*?)\s*尺码", str(title))
    return normalize_text(m.group(1)) if m else "未知"


def size_sort_key(size):
    try:
        return float(size)
    except Exception:
        return 999


def merge_sizes(series):
    sizes = [str(x).strip() for x in series if str(x).strip() and str(x).strip() != "未知"]
    return " ".join(sorted(sizes, key=size_sort_key))


def rule_score(rule, short_name, title, raw_spec):
    kw = normalize_text(rule.get("keyword", ""))
    if not kw:
        return -1

    field = rule.get("field", "全部")
    targets = []

    if field == "商品简称":
        targets = [(normalize_text(short_name), 1000)]
    elif field == "销售规格":
        targets = [(normalize_text(raw_spec), 700)]
    elif field == "货品标题":
        targets = [(normalize_text(title), 500)]
    else:
        targets = [
            (normalize_text(short_name), 1000),
            (normalize_text(raw_spec), 700),
            (normalize_text(title), 500)
        ]

    best = -1
    for text, weight in targets:
        if kw in text:
            best = max(best, weight + len(kw))
    return best


def detect_category(short_name, title, raw_spec, rules):
    category = "未分类"
    best = -1
    for r in rules:
        score = rule_score(r, short_name, title, raw_spec)
        if score > best:
            category = r.get("category", "未分类")
            best = score
    return category


def clean_spec(raw_spec, category, rules):
    spec = normalize_text(raw_spec)
    words = []
    for r in rules:
        if normalize_text(r.get("category", "")) == normalize_text(category):
            remove_words = str(r.get("remove_words", "")).strip()
            if remove_words:
                for w in remove_words.replace("，", ",").split(","):
                    w = normalize_text(w)
                    if w and w not in words:
                        words.append(w)
    for w in words:
        spec = spec.replace(w, "")
    return spec if spec else raw_spec


def get_stall(category, stall_map):
    return stall_map.get(normalize_text(category), "未设置档口")


def safe_sheet_name(name):
    name = re.sub(r'[\\/:*?\[\]]', "_", str(name).strip())
    return name[:31] if name else "未设置档口"


def prepare_image(image_b64, category, spec):
    temp_dir = get_temp_dir()
    raw = os.path.join(temp_dir, f"{safe_filename(category)}_{safe_filename(spec)}_raw")
    png = os.path.join(temp_dir, f"{safe_filename(category)}_{safe_filename(spec)}.png")
    base64_to_image_file(image_b64, raw)
    return prepare_image_file(raw, category, spec)


def prepare_image_file(source_path, category, spec):
    temp_dir = get_temp_dir()
    png = os.path.join(temp_dir, f"{safe_filename(category)}_{safe_filename(spec)}.png")

    img = PILImage.open(source_path)
    if img.mode in ("RGBA", "LA"):
        bg = PILImage.new("RGBA", img.size, (255,255,255,255))
        bg.paste(img, mask=img.getchannel("A"))
        img = bg.convert("RGB")
    else:
        img = img.convert("RGB")
    img.thumbnail((IMAGE_WIDTH_PX, IMAGE_HEIGHT_PX), PILImage.LANCZOS)
    canvas = PILImage.new("RGB", (IMAGE_WIDTH_PX, IMAGE_HEIGHT_PX), (255,255,255))
    canvas.paste(img, ((IMAGE_WIDTH_PX-img.width)//2, (IMAGE_HEIGHT_PX-img.height)//2))
    canvas.save(png)
    return png


def prepare_image_item(item, category, spec):
    if not item:
        return ""

    image_file = item.get("image_file") or item.get("file") or ""
    if image_file:
        source = image_file
        if not os.path.isabs(source):
            source = os.path.join(get_data_dir(), image_file)
        if os.path.exists(source):
            return prepare_image_file(source, category, spec)

    image_b64 = item.get("image_base64")
    if image_b64:
        return prepare_image(image_b64, category, spec)

    return ""


def style_and_images(output_file, image_map):
    matcher = ImageMatcher(image_map)
    wb = load_workbook(output_file)
    for ws in wb.worksheets:
        headers = {normalize_text(ws.cell(row=1, column=c).value): c for c in range(1, ws.max_column+1)}
        cat_col = headers.get("分类", 1)
        spec_col = headers.get("规格", 2)
        img_col = headers.get("图片", 3)
        img_letter = ws.cell(row=1, column=img_col).column_letter

        header_fill = PatternFill("solid", fgColor="1F4E78")
        header_font = Font(color="FFFFFF", bold=True)
        thin = Side(style="thin", color="D9E2F3")
        border = Border(left=thin, right=thin, top=thin, bottom=thin)

        for cell in ws[1]:
            cell.fill = header_fill
            cell.font = header_font
            cell.alignment = Alignment(horizontal="center", vertical="center")
            cell.border = border

        for c in range(1, ws.max_column+1):
            ws.column_dimensions[ws.cell(row=1, column=c).column_letter].width = 18
        ws.column_dimensions[img_letter].width = 20

        for row in range(2, ws.max_row+1):
            ws.row_dimensions[row].height = IMAGE_HEIGHT_PX * 0.75
            for col in range(1, ws.max_column+1):
                cell = ws.cell(row=row, column=col)
                cell.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
                cell.border = border

            cat = normalize_text(ws.cell(row=row, column=cat_col).value)
            spec = normalize_text(ws.cell(row=row, column=spec_col).value)
            item = matcher.find(cat, spec)
            if item:
                try:
                    path = prepare_image_item(item, cat, spec)
                    if path:
                        img = XLImage(path)
                        img.width = IMAGE_WIDTH_PX
                        img.height = IMAGE_HEIGHT_PX
                        ws.add_image(img, f"{img_letter}{row}")
                        ws.cell(row=row, column=img_col).value = ""
                except Exception:
                    ws.cell(row=row, column=img_col).value = ""
    wb.save(output_file)


def generate(files: List[str], output_mode: str, system: dict, template_name: str = ''):
    rules = system.get("category_rules", [])
    stall_map = system.get("stall_map", {})
    templates = system.get("import_templates", [])
    active_name = template_name or system.get("active_template", "")
    template = next((t for t in templates if t.get("name") == active_name), templates[0] if templates else None)

    if not template:
        raise ValueError("后端未配置导入模板")
    if not rules:
        raise ValueError("后端未配置分类规则")

    df = pd.concat([read_by_template(f, template) for f in files], ignore_index=True)
    df["原始规格"] = df["货品标题"].apply(extract_raw_spec)
    df["尺码"] = df["货品标题"].apply(extract_size)
    df["分类"] = df.apply(lambda r: detect_category(r.get("商品简称", ""), r["货品标题"], r["原始规格"], rules), axis=1)
    df["规格"] = df.apply(lambda r: clean_spec(r["原始规格"], r["分类"], rules), axis=1)
    df["档口"] = df["分类"].apply(lambda c: get_stall(c, stall_map))

    result = (
        df.groupby(["档口", "分类", "规格"], dropna=False)
        .apply(lambda g: pd.Series({
            "尺码": merge_size_quantity(g),
            "数量": sum(normalize_qty(v) for v in g["数量"])
        }))
        .reset_index()
        .sort_values(by=["档口", "分类", "规格"])
    )

    used_categories = sorted({normalize_text(c) for c in result["分类"].dropna().tolist() if normalize_text(c)})
    image_map = load_image_map_for_categories(system, used_categories)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = get_output_dir()

    if output_mode == "合并一个Sheet":
        out = os.path.join(out_dir, f"订单整理文档_合并_{ts}.xlsx")
        out_df = result[["档口","分类","规格","尺码","数量"]].copy()
        out_df.insert(3, "图片", "")
        with pd.ExcelWriter(out, engine="openpyxl") as writer:
            out_df.to_excel(writer, sheet_name="全部订单", index=False)
        style_and_images(out, image_map)
        return out

    if output_mode == "按档口分文档":
        batch = os.path.join(out_dir, f"订单整理文档_按档口分文档_{ts}")
        os.makedirs(batch, exist_ok=True)
        for stall, stall_df in result.groupby("档口", dropna=False):
            out = os.path.join(batch, f"{safe_sheet_name(stall)}_{ts}.xlsx")
            out_df = stall_df[["分类","规格","尺码","数量"]].copy()
            out_df.insert(2, "图片", "")
            with pd.ExcelWriter(out, engine="openpyxl") as writer:
                out_df.to_excel(writer, sheet_name=safe_sheet_name(stall), index=False)
            style_and_images(out, image_map)
        return batch

    out = os.path.join(out_dir, f"订单整理文档_分Sheet_{ts}.xlsx")
    with pd.ExcelWriter(out, engine="openpyxl") as writer:
        for stall, stall_df in result.groupby("档口", dropna=False):
            out_df = stall_df[["分类","规格","尺码","数量"]].copy()
            out_df.insert(2, "图片", "")
            out_df.to_excel(writer, sheet_name=safe_sheet_name(stall), index=False)
    style_and_images(out, image_map)
    return out


@app.post("/api/generate")
async def api_generate(
    files: List[UploadFile] = File(...),
    output_mode: str = Form("按档口分Sheet"),
    template_name: str = Form("")
):
    system, system_id = get_current_system()

    if not system:
        return JSONResponse({"ok": False, "web_version": WEB_VERSION, "error": "未配置整理系统", "debug": debug_environment()}, status_code=403)

    if not template_name:
        return JSONResponse({"ok": False, "web_version": WEB_VERSION, "error": "请先选择导入模板", "debug": debug_environment()}, status_code=400)

    if output_mode not in ALLOWED_OUTPUT_MODES:
        return JSONResponse({"ok": False, "web_version": WEB_VERSION, "error": "输出方式无效", "debug": debug_environment()}, status_code=400)

    saved = []
    try:
        for file in files:
            suffix = os.path.splitext(file.filename)[1] or ".xlsx"
            path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4().hex}{suffix}")
            with open(path, "wb") as f:
                f.write(await file.read())
            saved.append(path)

        output = generate_order_file(saved, system, output_mode, template_name)
        filename = os.path.basename(output)
        is_dir = os.path.isdir(output)
        download_path = zip_output_folder(output) if is_dir else output
        return {
            "ok": True,
            "web_version": WEB_VERSION,
            "path": output,
            "filename": filename,
            "is_dir": is_dir,
            "download_path": download_path,
            "download_filename": os.path.basename(download_path),
            "debug": debug_environment(),
        }
    except Exception as e:
        return JSONResponse({"ok": False, "web_version": WEB_VERSION, "error": str(e), "traceback": traceback.format_exc(), "debug": debug_environment()}, status_code=400)
    finally:
        for path in saved:
            try:
                if os.path.exists(path):
                    os.remove(path)
            except Exception:
                pass


@app.get("/api/download")
def download(path: str):
    if not is_path_under(path, get_output_dir()):
        return JSONResponse({"ok": False, "error": "只能下载输出目录内的文件"}, status_code=403)
    if not os.path.exists(path) or os.path.isdir(path):
        return JSONResponse({"ok": False, "error": "文件不存在或不是单个文件"}, status_code=404)
    return FileResponse(path, filename=os.path.basename(path))


@app.get("/api/open-output")
def open_output():
    os.startfile(get_output_dir())
    return {"ok": True}
