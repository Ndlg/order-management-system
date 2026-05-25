import os
import json
import base64
import hashlib
import shutil
import zlib
import secrets
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None


# ==================================================
# 关键：保持兼容旧数据
# ==================================================
APP_SECRET = "order-sorter-local-secure-key-v1"

APP_SECRETS = [
    "order-sorter-local-secure-key-v1",
    "order-sorter-local-secure-key-v2",
]

DATA_DIR_NAME = "data"
DATA_FILE_NAME = "system_data.enc"
TEMPLATE_FILE_NAME = "import_templates.json"
DATA_SCHEMA_VERSION = "7.5.1-lite"


def get_base_dir():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def get_data_dir():
    path = os.path.join(get_base_dir(), DATA_DIR_NAME)
    os.makedirs(path, exist_ok=True)
    return path


def get_data_file():
    return os.path.join(get_data_dir(), DATA_FILE_NAME)


def get_template_file():
    return os.path.join(get_data_dir(), TEMPLATE_FILE_NAME)


def get_output_dir():
    path = os.path.join(get_base_dir(), "output")
    os.makedirs(path, exist_ok=True)
    return path


def get_temp_dir():
    path = os.path.join(get_base_dir(), "temp")
    os.makedirs(path, exist_ok=True)
    return path


def make_fernet(secret=None):
    if Fernet is None:
        raise RuntimeError("缺少 cryptography，请执行：python -m pip install cryptography")

    if secret is None:
        secret = APP_SECRET

    digest = hashlib.sha256(secret.encode("utf-8")).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


# ==================================================
# 密码/用户兼容
# ==================================================
def hash_password(password, salt=None):
    if salt is None:
        salt = secrets.token_hex(16)

    raw = (salt + str(password)).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    return f"{salt}${digest}"


def verify_password(password, stored):
    try:
        salt, digest = str(stored).split("$", 1)
        return hash_password(password, salt) == stored
    except Exception:
        return False


# ==================================================
# 默认结构
# ==================================================
def default_import_templates():
    return [
        {
            "name": "1688新版-表头模式",
            "mode": "表头",
            "short_name": "商品简称",
            "spec": "销售规格",
            "qty": "商品数量",
            "remark": "备注",
            "item_sep": ";",
            "spec_split": "，"
        },
        {
            "name": "旧版-SV列模式",
            "mode": "列号",
            "title_col": "S",
            "qty_col": "V",
            "item_sep": ";",
            "spec_split": "，"
        }
    ]


def default_system():
    return {
        "name": "默认整理系统",
        "category_rules": [],
        "stall_map": {},
        # V7.5.1 起图片关系不再进入主数据文件，只保留空字段兼容旧代码入口。
        "image_map": {},
        "import_templates": default_import_templates(),
        "active_template": ""
    }


def default_data():
    system = default_system()

    data = {
        "schema_version": DATA_SCHEMA_VERSION,
        "active_system": "default",
        "systems": {
            "default": system
        },
        "users": {
            "admin": {
                "password_hash": hash_password("admin123"),
                "role": "admin",
                "system_id": "default"
            }
        }
    }

    # 兼容旧Web读取方式：顶层也保留一份当前系统数据
    data.update(system)

    return data


def normalize_system(system, name="默认整理系统"):
    if not isinstance(system, dict):
        system = {}

    system.setdefault("name", name)
    system.setdefault("category_rules", [])
    system.setdefault("stall_map", {})
    # V7.5.1 放弃旧版巨型 image_map 主库结构；图片关系只放在 data/image_categories/*.json。
    system["image_map"] = {}
    system.setdefault("import_templates", default_import_templates())
    system.setdefault("active_template", "1688新版-表头模式")

    if not isinstance(system.get("category_rules"), list):
        system["category_rules"] = []

    if not isinstance(system.get("stall_map"), dict):
        system["stall_map"] = {}

    if not isinstance(system.get("import_templates"), list):
        system["import_templates"] = default_import_templates()

    if not system.get("active_template"):
        if system.get("import_templates"):
            system["active_template"] = system["import_templates"][0].get("name", "1688新版-表头模式")
        else:
            system["active_template"] = "1688新版-表头模式"

    return system


def mirror_active_system_to_top(data):
    """
    关键兼容逻辑：
    Web旧版 app.py 是从顶层读取：
      data["category_rules"]
      data["stall_map"]
      data["image_map"]
      data["import_templates"]
      data["active_template"]

    新版后端是从 systems/default 读取。
    所以这里把当前系统镜像到顶层，避免Web控制台显示0条。
    """
    if not isinstance(data, dict):
        return data

    systems = data.get("systems", {})
    active_system = data.get("active_system", "default")

    if active_system not in systems and systems:
        active_system = next(iter(systems.keys()))
        data["active_system"] = active_system

    system = systems.get(active_system)

    if not system:
        return data

    system = normalize_system(system, system.get("name", active_system))
    data["systems"][active_system] = system

    data["category_rules"] = system.get("category_rules", [])
    data["stall_map"] = system.get("stall_map", {})
    data["image_map"] = {}
    data["import_templates"] = system.get("import_templates", default_import_templates())
    data["active_template"] = system.get("active_template", "1688新版-表头模式")

    return data


def normalize_data(data):
    if not isinstance(data, dict):
        return default_data()

    # ==================================================
    # 兼容旧版单系统结构
    # 旧结构一般是：
    # {
    #   "category_rules": [],
    #   "stall_map": {},
    #   "image_map": {},
    #   "import_templates": [],
    #   "active_template": "..."
    # }
    # ==================================================
    if "systems" not in data:
        old_system = {
            "name": "默认整理系统",
            "category_rules": data.get("category_rules", []),
            "stall_map": data.get("stall_map", {}),
            "image_map": {},
            "import_templates": data.get("import_templates", default_import_templates()),
            "active_template": data.get("active_template", "1688新版-表头模式")
        }

        data = {
            "active_system": "default",
            "systems": {
                "default": normalize_system(old_system)
            },
            "users": {
                "admin": {
                    "password_hash": hash_password("admin123"),
                    "role": "admin",
                    "system_id": "default"
                }
            }
        }

    data["schema_version"] = DATA_SCHEMA_VERSION
    data.setdefault("active_system", "default")
    data.setdefault("systems", {})
    data.setdefault("users", {})

    if "default" not in data["systems"]:
        data["systems"]["default"] = default_system()

    if "admin" not in data["users"]:
        data["users"]["admin"] = {
            "password_hash": hash_password("admin123"),
            "role": "admin",
            "system_id": "default"
        }

    for sid, system in list(data["systems"].items()):
        name = system.get("name", sid) if isinstance(system, dict) else sid
        data["systems"][sid] = normalize_system(system, name)

    if data["active_system"] not in data["systems"]:
        data["active_system"] = next(iter(data["systems"].keys()))

    return mirror_active_system_to_top(data)


def get_active_system(data):
    data = normalize_data(data)
    sid = data.get("active_system", "default")

    if sid not in data.get("systems", {}):
        sid = "default"

    return data["systems"][sid], sid


def get_system_for_user(data, username):
    data = normalize_data(data)

    user = data.get("users", {}).get(username)
    if not user:
        return None, None

    system_id = user.get("system_id", data.get("active_system", "default"))

    if system_id not in data.get("systems", {}):
        system_id = data.get("active_system", "default")

    return data.get("systems", {}).get(system_id), system_id


def get_user(data, username):
    data = normalize_data(data)
    return data.get("users", {}).get(username)


# ==================================================
# 读取/保存
# ==================================================
def load_data(auto_save_on_read=False, progress=None):
    def report(percent, message, detail=""):
        if progress:
            try:
                progress(percent, message, detail)
            except Exception:
                pass

    file_path = get_data_file()

    if not os.path.exists(file_path):
        report(8, "未发现主数据文件，创建轻量默认数据", file_path)
        data = default_data()
        save_data(data)
        report(100, "默认数据创建完成", file_path)
        return data

    size = os.path.getsize(file_path)
    report(10, "读取轻量主数据文件", f"{file_path} ({size / 1024 / 1024:.2f} MB)")
    encrypted = Path(file_path).read_bytes()
    report(35, "主数据文件读取完成", f"{len(encrypted) / 1024 / 1024:.2f} MB")

    # 依次尝试历史密钥
    for secret in APP_SECRETS:
        try:
            f = make_fernet(secret)
            decrypted = f.decrypt(encrypted)
            report(55, "解密完成", "正在解压并解析 JSON")

            try:
                raw = zlib.decompress(decrypted)
            except Exception:
                raw = decrypted
            report(70, "解压完成", f"{len(raw) / 1024 / 1024:.2f} MB")

            data = json.loads(raw.decode("utf-8"))
            report(82, "JSON 解析完成", "正在整理轻量结构")
            data = normalize_data(data)

            if auto_save_on_read:
                save_data(data)

            report(92, "轻量主数据准备完成", "图片关系稍后按分类懒加载")
            return data

        except Exception:
            continue

    # 全部失败，返回默认数据
    report(8, "主数据无法解密，创建轻量默认数据", file_path)
    data = default_data()
    save_data(data)
    report(100, "默认数据创建完成", file_path)
    return data



def load_templates_fast():
    """
    快速读取导入模板。
    优先读取轻量模板文件，避免“刷新模板”时读取/解密/压缩/重写整库。
    如果轻量文件不存在，则从主数据兼容读取一次并落地轻量文件。
    """
    template_file = get_template_file()

    if os.path.exists(template_file):
        try:
            raw = Path(template_file).read_text(encoding="utf-8-sig")
            templates = json.loads(raw)
            if isinstance(templates, list):
                return templates
        except Exception:
            pass

    try:
        data = load_data(auto_save_on_read=False)
        system, _ = get_active_system(data)
        templates = system.get("import_templates", []) if system else []
        save_templates_fast(templates)
        return templates
    except Exception:
        return []


def save_templates_fast(templates):
    """只保存模板轻量索引文件，不触发整库重写。"""
    try:
        os.makedirs(get_data_dir(), exist_ok=True)
        Path(get_template_file()).write_text(
            json.dumps(templates or [], ensure_ascii=False, indent=2),
            encoding="utf-8-sig"
        )
    except Exception:
        pass

def save_data(data):
    os.makedirs(get_data_dir(), exist_ok=True)

    data = normalize_data(data)
    data["schema_version"] = DATA_SCHEMA_VERSION

    # 如果顶层被旧版Web修改了，也同步回 active system
    active_system = data.get("active_system", "default")

    if active_system in data.get("systems", {}):
        system = data["systems"][active_system]
        system["category_rules"] = data.get("category_rules", system.get("category_rules", []))
        system["stall_map"] = data.get("stall_map", system.get("stall_map", {}))
        system["image_map"] = {}
        system["import_templates"] = data.get("import_templates", system.get("import_templates", default_import_templates()))
        system["active_template"] = data.get("active_template", system.get("active_template", "1688新版-表头模式"))
        data["systems"][active_system] = normalize_system(system)

    data["image_map"] = {}
    for system in data.get("systems", {}).values():
        if isinstance(system, dict):
            system["image_map"] = {}

    f = make_fernet(APP_SECRET)
    raw = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    encrypted = f.encrypt(zlib.compress(raw, level=9))

    Path(get_data_file()).write_bytes(encrypted)

    # 同步轻量模板文件，供一键整理前端快速刷新模板使用。
    try:
        active_system = data.get("active_system", "default")
        system = data.get("systems", {}).get(active_system, {})
        save_templates_fast(system.get("import_templates", []))
    except Exception:
        pass


# ==================================================
# 工具函数
# ==================================================
def normalize_text(value):
    return str(value).strip().replace(" ", "").replace("\u3000", "")


def normalize_match_text(value):
    text = normalize_text(value).casefold()
    return "".join(ch for ch in text if ch.isalnum() or "\u4e00" <= ch <= "\u9fff")


def make_image_key(category, spec):
    return f"{normalize_text(category)}|{normalize_text(spec)}"


def image_file_to_base64(path):
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def base64_to_image_file(b64, out_path):
    data = base64.b64decode(b64.encode("utf-8"))
    with open(out_path, "wb") as f:
        f.write(data)


def safe_filename(name):
    import re
    name = normalize_text(name)
    return re.sub(r'[\\/:*?"<>|]', "_", name)


def col_letter_to_index(letter):
    letter = str(letter).strip().upper()
    result = 0

    for ch in letter:
        if "A" <= ch <= "Z":
            result = result * 26 + ord(ch) - ord("A") + 1

    return result - 1


# ==================================================
# V2兼容优化：旧数据体检、修复、图片索引/缓存
# ==================================================
def get_backup_dir():
    path = os.path.join(get_data_dir(), "backup")
    os.makedirs(path, exist_ok=True)
    return path


def get_images_dir():
    path = os.path.join(get_data_dir(), "images")
    os.makedirs(path, exist_ok=True)
    return path


def get_image_category_dir():
    """分类图片关系分片目录。用于按分类懒加载图片关系，避免每次整理都扫描全量图片。"""
    path = os.path.join(get_data_dir(), "image_categories")
    os.makedirs(path, exist_ok=True)
    return path


def _image_category_file(category):
    filename = safe_filename(category) or "未分类"
    return os.path.join(get_image_category_dir(), f"{filename}.json")


def _image_ext_from_name(name, default=".png"):
    ext = os.path.splitext(str(name or ""))[1].lower()
    if ext in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return ext
    return default


def write_image_bytes(raw, filename="image.png"):
    """把图片二进制按内容哈希存到 data/images，返回相对路径。"""
    if not raw:
        return ""

    digest = hashlib.sha1(raw).hexdigest()
    ext = _image_ext_from_name(filename)
    rel = os.path.join("images", f"{digest}{ext}").replace("\\", "/")
    dst = os.path.join(get_data_dir(), rel)
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        with open(dst, "wb") as f:
            f.write(raw)
    return rel


def store_image_file(source_path):
    if not source_path or not os.path.exists(source_path):
        return ""
    with open(source_path, "rb") as f:
        return write_image_bytes(f.read(), os.path.basename(source_path))


def load_image_category_map(category):
    fp = _image_category_file(category)
    if not os.path.exists(fp):
        return {}
    try:
        raw = Path(fp).read_text(encoding="utf-8-sig")
        data = json.loads(raw)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def save_image_category_map(category, bucket):
    category = normalize_text(category)
    if not category:
        return ""

    cleaned = {}
    for raw_key, raw_item in (bucket or {}).items():
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        spec = normalize_text(item.get("spec", ""))
        item_category = normalize_text(item.get("category", category)) or category
        if not spec and isinstance(raw_key, str) and "|" in raw_key:
            item_category, spec = raw_key.split("|", 1)
            item_category = normalize_text(item_category) or category
            spec = normalize_text(spec)
        if not spec:
            continue
        item["category"] = item_category
        item["spec"] = spec
        item.pop("image_base64", None)
        cleaned[make_image_key(item_category, spec)] = item

    fp = _image_category_file(category)
    if cleaned:
        Path(fp).write_text(
            json.dumps(cleaned, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8-sig"
        )
    elif os.path.exists(fp):
        os.remove(fp)
    return fp


def upsert_image_binding(category, spec, source_path="", image_bytes=None, filename="image.png"):
    category = normalize_text(category)
    spec = normalize_text(spec)
    if not category or not spec:
        raise ValueError("分类和规格不能为空")

    if image_bytes is not None:
        image_file = write_image_bytes(image_bytes, filename)
    else:
        image_file = store_image_file(source_path)
    if not image_file:
        raise ValueError("图片文件无效")

    bucket = load_image_category_map(category)
    bucket[make_image_key(category, spec)] = {
        "category": category,
        "spec": spec,
        "filename": os.path.basename(filename or source_path or "image.png"),
        "image_file": image_file
    }
    save_image_category_map(category, bucket)
    return bucket[make_image_key(category, spec)]


def delete_image_binding(category, spec):
    category = normalize_text(category)
    spec = normalize_text(spec)
    bucket = load_image_category_map(category)
    removed = bucket.pop(make_image_key(category, spec), None)
    save_image_category_map(category, bucket)
    return bool(removed)


def clear_image_category(category):
    fp = _image_category_file(category)
    if os.path.exists(fp):
        os.remove(fp)


def clear_all_image_categories():
    out_dir = get_image_category_dir()
    for file in Path(out_dir).glob("*.json"):
        file.unlink()


def list_image_category_names():
    out_dir = get_image_category_dir()
    names = []
    for file in Path(out_dir).glob("*.json"):
        names.append(file.stem)
    return sorted(set(names))


def iter_image_bindings(category_filter="", keyword="", max_items=None):
    category_filter = normalize_text(category_filter)
    keyword = normalize_text(keyword)
    categories = list_image_category_names()
    if category_filter and category_filter != "全部分类":
        categories = [c for c in categories if normalize_text(c) == category_filter]

    shown = 0
    total = 0
    for category in categories:
        bucket = load_image_category_map(category)
        total += len(bucket)
        for raw_key, item in sorted(bucket.items()):
            if not isinstance(item, dict):
                continue
            cat = normalize_text(item.get("category", category))
            spec = normalize_text(item.get("spec", ""))
            if not spec and isinstance(raw_key, str) and "|" in raw_key:
                cat, spec = raw_key.split("|", 1)
                cat = normalize_text(cat)
                spec = normalize_text(spec)
            if keyword and keyword not in (cat + spec):
                continue
            yield make_image_key(cat, spec), item
            shown += 1
            if max_items and shown >= max_items:
                return


def image_storage_summary(count_entries=False):
    out_dir = get_image_category_dir()
    image_dir = get_images_dir()
    files = list(Path(out_dir).glob("*.json"))
    image_files = [file for file in Path(image_dir).glob("*") if file.is_file()]
    shard_bytes = sum(file.stat().st_size for file in files if file.exists())
    image_bytes = sum(file.stat().st_size for file in image_files if file.exists())
    total_bytes = shard_bytes + image_bytes
    entries = None
    if count_entries:
        entries = 0
        for file in files:
            try:
                data = json.loads(file.read_text(encoding="utf-8-sig"))
                if isinstance(data, dict):
                    entries += len(data)
            except Exception:
                pass
    return {
        "category_files": len(files),
        "image_files": len(image_files),
        "bytes": total_bytes,
        "shard_bytes": shard_bytes,
        "image_bytes": image_bytes,
        "entries": entries
    }


def save_image_category_cache(image_map):
    """把全量 image_map 拆成 分类 -> json 分片。兼容旧主库，不改变旧数据结构。"""
    if not isinstance(image_map, dict):
        return
    buckets = {}
    for raw_key, raw_item in image_map.items():
        if not isinstance(raw_item, dict):
            continue
        item = dict(raw_item)
        category = item.get("category", "")
        spec = item.get("spec", "")
        if (not category or not spec) and isinstance(raw_key, str) and "|" in raw_key:
            category, spec = raw_key.split("|", 1)
        category = normalize_text(category)
        spec = normalize_text(spec)
        if not category or not spec:
            continue
        item["category"] = category
        item["spec"] = spec
        if item.get("image_base64") and not item.get("image_file"):
            image_file = decode_image_base64_to_file(item.get("image_base64"), category, spec)
            if image_file:
                item["image_file"] = image_file
        item.pop("image_base64", None)
        buckets.setdefault(category, {})[make_image_key(category, spec)] = item

    out_dir = get_image_category_dir()
    for category, bucket in buckets.items():
        Path(_image_category_file(category)).write_text(
            json.dumps(bucket, ensure_ascii=False, separators=(",", ":")),
            encoding="utf-8-sig"
        )


def load_image_map_for_categories(system, categories):
    """
    只加载指定分类的图片关系。
    V7.5.1 起只读取 data/image_categories/<分类>.json，不再扫描主库 image_map。
    """
    categories_norm = {normalize_text(c) for c in (categories or []) if normalize_text(c)}
    if not categories_norm:
        return {}

    merged = {}
    for category in categories_norm:
        fp = _image_category_file(category)
        if os.path.exists(fp):
            try:
                raw = Path(fp).read_text(encoding="utf-8-sig")
                data = json.loads(raw)
                if isinstance(data, dict):
                    merged.update(data)
                    continue
            except Exception:
                pass
    return merged


def backup_data_file():
    import shutil
    from datetime import datetime

    src = get_data_file()
    if not os.path.exists(src):
        return ""

    name = "system_data_" + datetime.now().strftime("%Y%m%d_%H%M%S") + ".enc"
    dst = os.path.join(get_backup_dir(), name)
    shutil.copy2(src, dst)
    return dst


def decode_image_base64_to_file(image_base64, category, spec, ext=".png"):
    if not image_base64:
        return ""

    try:
        raw = base64.b64decode(str(image_base64).encode("utf-8"))
    except Exception:
        return ""

    digest = hashlib.sha1(raw).hexdigest()
    filename = f"{digest}{ext if ext.startswith('.') else '.' + ext}"
    rel = os.path.join("images", filename).replace("\\", "/")
    dst = os.path.join(get_data_dir(), rel)

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    if not os.path.exists(dst):
        with open(dst, "wb") as f:
            f.write(raw)

    return rel


def get_image_absolute_path(item):
    if not isinstance(item, dict):
        return ""

    image_file = item.get("image_file") or item.get("file") or ""
    if image_file:
        path = image_file
        if not os.path.isabs(path):
            path = os.path.join(get_data_dir(), image_file)
        return path

    return ""


def build_image_lookup(image_map):
    """
    构建图片查询索引：
    1. 精确key：分类|规格
    2. 同分类桶：分类 -> 图片列表
    """
    by_key = {}
    by_category = {}

    if not isinstance(image_map, dict):
        return by_key, by_category

    for raw_key, raw_item in image_map.items():
        if not isinstance(raw_item, dict):
            continue

        category = raw_item.get("category", "")
        spec = raw_item.get("spec", "")

        if not category or not spec:
            if isinstance(raw_key, str) and "|" in raw_key:
                category, spec = raw_key.split("|", 1)

        category = normalize_text(category)
        spec = normalize_text(spec)
        if not category or not spec:
            continue

        item = dict(raw_item)
        item["category"] = category
        item["spec"] = spec

        key = make_image_key(category, spec)
        by_key[key] = item
        by_category.setdefault(category, []).append(item)

    # 同分类下优先匹配更长规格，避免“黑”误命中“黑色加绒”
    for category, items in by_category.items():
        items.sort(key=lambda x: len(normalize_text(x.get("spec", ""))), reverse=True)

    return by_key, by_category


class ImageMatcher:
    """
    图片匹配器：
    - 精确索引 O(1)
    - 同分类小范围遍历兜底
    - 结果缓存，避免同一规格重复扫描
    """
    def __init__(self, image_map):
        self.by_key, self.by_category = build_image_lookup(image_map)
        self.cache = {}

    def _continuous_match(self, item_spec, query_text):
        item_compact = normalize_match_text(item_spec)
        query_compact = normalize_match_text(query_text)
        if not item_compact or not query_compact:
            return False

        min_len = 2
        if len(item_compact) >= min_len and item_compact in query_compact:
            return True
        if len(query_compact) >= min_len and query_compact in item_compact:
            return True
        return False

    def find(self, category, spec, *extra_texts):
        category_norm = normalize_text(category)
        spec_norm = normalize_text(spec)
        query_texts = [spec_norm] + [normalize_text(x) for x in extra_texts if normalize_text(x)]
        cache_key = (category_norm, tuple(query_texts))

        if cache_key in self.cache:
            return self.cache[cache_key]

        exact_key = make_image_key(category_norm, spec_norm)
        item = self.by_key.get(exact_key)
        if item:
            self.cache[cache_key] = item
            return item

        candidates = self.by_category.get(category_norm, [])
        for candidate in candidates:
            item_spec = normalize_text(candidate.get("spec", ""))

            if not item_spec:
                continue

            if item_spec == spec_norm:
                self.cache[cache_key] = candidate
                return candidate

            for query_text in query_texts:
                if self._continuous_match(item_spec, query_text):
                    self.cache[cache_key] = candidate
                    return candidate

        self.cache[cache_key] = None
        return None


def normalize_image_map(image_map, migrate_base64=False):
    """
    修复旧图片关系：
    - key统一为 分类|规格
    - 补齐 category/spec
    - 可选把 image_base64 落盘为 data/images 文件
    """
    fixed = {}
    report = {
        "total": 0,
        "valid": 0,
        "invalid": 0,
        "duplicates": 0,
        "migrated_images": 0
    }

    if not isinstance(image_map, dict):
        return fixed, report

    for raw_key, raw_item in image_map.items():
        report["total"] += 1

        if not isinstance(raw_item, dict):
            report["invalid"] += 1
            continue

        item = dict(raw_item)
        category = item.get("category", "")
        spec = item.get("spec", "")

        if (not category or not spec) and isinstance(raw_key, str) and "|" in raw_key:
            k_cat, k_spec = raw_key.split("|", 1)
            category = category or k_cat
            spec = spec or k_spec

        category = normalize_text(category)
        spec = normalize_text(spec)

        if not category or not spec:
            report["invalid"] += 1
            continue

        item["category"] = category
        item["spec"] = spec

        if migrate_base64 and item.get("image_base64") and not item.get("image_file"):
            image_file = decode_image_base64_to_file(item.get("image_base64"), category, spec)
            if image_file:
                item["image_file"] = image_file
                report["migrated_images"] += 1

        key = make_image_key(category, spec)
        if key in fixed:
            report["duplicates"] += 1

        fixed[key] = item
        report["valid"] += 1

    return fixed, report


def repair_system_data(data, migrate_images=True):
    """
    整理/修复旧数据：
    - 备份由调用方执行
    - 保持旧字段可用
    - 新增/重建规范图片索引
    """
    data = normalize_data(data)
    summary = {
        "systems": 0,
        "templates": 0,
        "rules": 0,
        "stalls": 0,
        "images_total": 0,
        "images_valid": 0,
        "images_invalid": 0,
        "images_duplicates": 0,
        "images_migrated": 0
    }

    for sid, system in data.get("systems", {}).items():
        system = normalize_system(system, system.get("name", sid))
        summary["systems"] += 1

        # 模板补齐
        templates = []
        seen_templates = set()
        for t in system.get("import_templates", []):
            if not isinstance(t, dict):
                continue
            name = str(t.get("name", "")).strip()
            if not name or name in seen_templates:
                continue
            seen_templates.add(name)
            mode = t.get("mode", "表头") or "表头"
            if mode == "表头":
                t.setdefault("short_name", "商品简称")
                t.setdefault("spec", "销售规格")
                t.setdefault("qty", "商品数量")
                t.setdefault("remark", "备注")
            else:
                t.setdefault("title_col", "S")
                t.setdefault("qty_col", "V")
                t.setdefault("remark_col", "")
            t.setdefault("item_sep", ";")
            t.setdefault("spec_split", "，")
            templates.append(t)
        if not templates:
            templates = default_import_templates()
        system["import_templates"] = templates
        summary["templates"] += len(templates)

        # 分类规则清洗
        fixed_rules = []
        seen_rules = set()
        for r in system.get("category_rules", []):
            if not isinstance(r, dict):
                continue
            category = normalize_text(r.get("category", ""))
            keyword = normalize_text(r.get("keyword", ""))
            if not category or not keyword:
                continue
            field = r.get("field", "全部") or "全部"
            remove_words = str(r.get("remove_words", "") or "")
            rk = (category, keyword, field, remove_words)
            if rk in seen_rules:
                continue
            seen_rules.add(rk)
            fixed_rules.append({
                "category": category,
                "keyword": keyword,
                "field": field,
                "remove_words": remove_words
            })
        system["category_rules"] = fixed_rules
        summary["rules"] += len(fixed_rules)

        # 档口映射清洗
        fixed_stalls = {}
        for cat, stall in (system.get("stall_map", {}) or {}).items():
            cat_n = normalize_text(cat)
            stall_n = str(stall).strip()
            if cat_n and stall_n:
                fixed_stalls[cat_n] = stall_n
        system["stall_map"] = fixed_stalls
        summary["stalls"] += len(fixed_stalls)

        # 图片索引重建
        fixed_images, image_report = normalize_image_map(system.get("image_map", {}), migrate_base64=migrate_images)
        system["image_map"] = fixed_images
        summary["images_total"] += image_report["total"]
        summary["images_valid"] += image_report["valid"]
        summary["images_invalid"] += image_report["invalid"]
        summary["images_duplicates"] += image_report["duplicates"]
        summary["images_migrated"] += image_report["migrated_images"]

        # 不再由后端控制当前模板，但字段保留兼容
        system["active_template"] = ""

        data["systems"][sid] = system

    return mirror_active_system_to_top(data), summary


def preview_data_summary(data=None, max_items=8):
    if data is None:
        data = load_data()
    data = normalize_data(data)
    system, sid = get_active_system(data)

    templates = system.get("import_templates", [])
    rules = system.get("category_rules", [])
    stalls = system.get("stall_map", {})
    image_stats = image_storage_summary(count_entries=True)
    image_categories = list_image_category_names()

    return {
        "system_id": sid,
        "system_name": system.get("name", sid),
        "templates_count": len(templates),
        "rules_count": len(rules),
        "stalls_count": len(stalls),
        "images_count": image_stats.get("entries") or 0,
        "image_category_files": image_stats.get("category_files", 0),
        "image_storage_mb": round((image_stats.get("bytes", 0) or 0) / 1024 / 1024, 2),
        "templates_preview": [t.get("name", "") for t in templates[:max_items] if isinstance(t, dict)],
        "rules_preview": [
            f"{r.get('category', '')} / {r.get('keyword', '')}"
            for r in rules[:max_items]
            if isinstance(r, dict)
        ],
        "images_preview": image_categories[:max_items]
    }
