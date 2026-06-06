import os
import json
import base64
import hashlib
import shutil
import zlib
import secrets
import re
from pathlib import Path

try:
    from cryptography.fernet import Fernet
except Exception:
    Fernet = None

from waybill_raw_contract import (
    LEGACY_RAW_WAYBILL_TEMPLATE_NAMES,
    PROCESSED_WAYBILL_TEMPLATE_NAME,
    RAW_WAYBILL_MODE,
    RAW_WAYBILL_TEMPLATE_NAME,
    RAW_WAYBILL_TEXT_COLUMN,
)
from waybill_text_parser import default_rule_config, normalize_rule_config


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
DEV_WORKSPACE_DIR_NAME = "_实验开发区"
DATA_DIR_OVERRIDE_ENV = "ORDER_SORTER_DATA_DIR"
OUTPUT_DIR_OVERRIDE_ENV = "ORDER_SORTER_OUTPUT_DIR"
TEMP_DIR_OVERRIDE_ENV = "ORDER_SORTER_TEMP_DIR"


def get_base_dir():
    import sys
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def _shared_project_data_dir(base_dir):
    current = Path(base_dir).resolve()
    for folder in (current, *current.parents):
        if folder.name == DEV_WORKSPACE_DIR_NAME:
            shared_data = folder.parent / DATA_DIR_NAME
            if shared_data.exists():
                return str(shared_data)
    return None


def _shared_project_output_dir(base_dir):
    current = Path(base_dir).resolve()
    for folder in (current, *current.parents):
        if folder.name == DEV_WORKSPACE_DIR_NAME:
            return str(folder.parent / "output")
    return None


def _source_project_root(base_dir):
    current = Path(base_dir).resolve()
    for folder in (current, *current.parents):
        if folder.name == "src" and (folder.parent / "data").exists():
            return folder.parent
        if (folder / "src").exists() and (folder / "data").exists():
            return folder
    return None


def get_data_dir():
    override = os.environ.get(DATA_DIR_OVERRIDE_ENV, "").strip()
    if override:
        path = os.path.abspath(os.path.expanduser(override))
    else:
        project_root = _source_project_root(get_base_dir())
        path = (
            _shared_project_data_dir(get_base_dir())
            or (str(project_root / DATA_DIR_NAME) if project_root else None)
            or os.path.join(get_base_dir(), DATA_DIR_NAME)
        )
    os.makedirs(path, exist_ok=True)
    return path


def get_data_file():
    return os.path.join(get_data_dir(), DATA_FILE_NAME)


def get_template_file():
    return os.path.join(get_data_dir(), TEMPLATE_FILE_NAME)


def get_output_dir():
    override = os.environ.get(OUTPUT_DIR_OVERRIDE_ENV, "").strip()
    if override:
        path = os.path.abspath(os.path.expanduser(override))
    else:
        project_root = _source_project_root(get_base_dir())
        path = (
            _shared_project_output_dir(get_base_dir())
            or (str(project_root / "data" / "output") if project_root else None)
            or os.path.join(get_base_dir(), "output")
        )
    os.makedirs(path, exist_ok=True)
    return path


def get_temp_dir():
    override = os.environ.get(TEMP_DIR_OVERRIDE_ENV, "").strip()
    if override:
        path = os.path.abspath(os.path.expanduser(override))
    else:
        project_root = _source_project_root(get_base_dir())
        path = str(project_root / "tmp") if project_root else os.path.join(get_base_dir(), "temp")
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
WAYBILL_TEMPLATE_NAME = RAW_WAYBILL_TEMPLATE_NAME
WAYBILL_IMPORT_TEMPLATE = {
    "name": WAYBILL_TEMPLATE_NAME,
    "mode": RAW_WAYBILL_MODE,
    "raw_text": RAW_WAYBILL_TEXT_COLUMN,
    "short_name": RAW_WAYBILL_TEXT_COLUMN,
    "spec": "",
    "size": "",
    "qty": "",
    "remark": "",
    "item_sep": ";",
    "spec_split": "，",
}
WAYBILL_PROCESSED_TEMPLATE_NAME = PROCESSED_WAYBILL_TEMPLATE_NAME
WAYBILL_PROCESSED_IMPORT_TEMPLATE = {
    "name": WAYBILL_PROCESSED_TEMPLATE_NAME,
    "mode": "表头",
    "short_name": "商品简称",
    "spec": "规格",
    "size": "尺码",
    "qty": "数量",
    "remark": "",
    "item_sep": ";",
    "spec_split": "，",
}
REMOVED_IMPORT_TEMPLATE_NAMES = {
    WAYBILL_TEMPLATE_NAME,
    *LEGACY_RAW_WAYBILL_TEMPLATE_NAMES,
    "旧版-SV列模式",
}


def default_import_templates():
    return [
        {
            "name": "1688新版-表头模式",
            "mode": "表头",
            "short_name": "商品简称",
            "spec": "销售规格",
            "size": "",
            "qty": "商品数量",
            "remark": "备注",
            "item_sep": ";",
            "spec_split": "，"
        },
        dict(WAYBILL_PROCESSED_IMPORT_TEMPLATE),
    ]


def ensure_default_import_templates(templates):
    result = []
    seen = set()
    if isinstance(templates, list):
        for template in templates:
            if not isinstance(template, dict):
                continue
            original_name = str(template.get("name") or "").strip()
            name = WAYBILL_TEMPLATE_NAME if original_name in LEGACY_RAW_WAYBILL_TEMPLATE_NAMES else original_name
            mode = str(template.get("mode") or "").strip()
            if name in REMOVED_IMPORT_TEMPLATE_NAMES or mode == RAW_WAYBILL_MODE:
                continue
            if not name or name in seen:
                continue
            item = dict(template)
            if name == WAYBILL_PROCESSED_TEMPLATE_NAME and any(item.get(key) != value for key, value in WAYBILL_PROCESSED_IMPORT_TEMPLATE.items()):
                item.update(WAYBILL_PROCESSED_IMPORT_TEMPLATE)
            result.append(item)
            seen.add(name)

    for template in default_import_templates():
        name = template.get("name", "")
        if name and name not in seen:
            result.append(dict(template))
            seen.add(name)
    return result


def default_system():
    return {
        "name": "默认整理系统",
        "category_rules": [],
        "waybill_parse_rules": default_rule_config(),
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
    system["waybill_parse_rules"] = normalize_rule_config(system.get("waybill_parse_rules"))
    system.setdefault("stall_map", {})
    # V7.5.1 放弃旧版巨型 image_map 主库结构；图片关系只放在 data/image_categories/*.json。
    system["image_map"] = {}
    system.setdefault("import_templates", default_import_templates())
    system.setdefault("active_template", "1688新版-表头模式")

    if not isinstance(system.get("category_rules"), list):
        system["category_rules"] = []
    else:
        normalized_rules = []
        for rule in system["category_rules"]:
            if not isinstance(rule, dict):
                continue
            item = dict(rule)
            item.setdefault("output_shoe", item.get("shoe_name", ""))
            normalized_rules.append(item)
        system["category_rules"] = normalized_rules
    system.pop("waybill_recognition_rules", None)

    if not isinstance(system.get("stall_map"), dict):
        system["stall_map"] = {}

    if not isinstance(system.get("import_templates"), list):
        system["import_templates"] = default_import_templates()
    else:
        system["import_templates"] = ensure_default_import_templates(system.get("import_templates"))

    if system.get("active_template") in REMOVED_IMPORT_TEMPLATE_NAMES:
        system["active_template"] = WAYBILL_PROCESSED_TEMPLATE_NAME

    template_names = {str(t.get("name", "") or "").strip() for t in system.get("import_templates", []) if isinstance(t, dict)}
    if not system.get("active_template") or system.get("active_template") not in template_names:
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
    data["waybill_parse_rules"] = system.get("waybill_parse_rules", default_rule_config())
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
            "waybill_parse_rules": data.get("waybill_parse_rules", default_rule_config()),
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
                return ensure_default_import_templates(templates)
        except Exception:
            pass

    try:
        data = load_data(auto_save_on_read=False)
        system, _ = get_active_system(data)
        templates = system.get("import_templates", []) if system else []
        templates = ensure_default_import_templates(templates)
        save_templates_fast(templates)
        return templates
    except Exception:
        return []


def save_templates_fast(templates):
    """只保存模板轻量索引文件，不触发整库重写。"""
    try:
        os.makedirs(get_data_dir(), exist_ok=True)
        templates = ensure_default_import_templates(templates)
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
        system["waybill_parse_rules"] = data.get("waybill_parse_rules", system.get("waybill_parse_rules", default_rule_config()))
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


IMAGE_MATCH_NOISE_WORDS = (
    "近期热销",
    "近期热卖",
    "热销款",
    "爆款推荐",
    "爆款",
    "热销",
    "热卖",
    "主推款",
    "主推",
    "推荐",
    "现货",
    "到货",
    "补货",
    "新款",
    "特价",
    "低价",
    "活动",
    "折扣",
    "清仓",
)


IMAGE_MATCH_REMARK_WORDS = (
    "订单备注",
    "买家留言",
    "卖家备注",
    "商家备注",
    "客户备注",
    "备注",
    "手填",
    "手写",
    "报货",
    "拿货",
    "发货",
    "换货",
    "换",
    "sku",
    "SKU",
    "款号",
    "款式",
    "鞋款",
    "货号",
    "颜色分类",
    "颜色",
    "规格",
    "尺码",
    "码数",
    "鞋码",
    "size",
    "SIZE",
)


IMAGE_MATCH_SPLIT_RE = re.compile(r"[\s,，;；/\\|、。.!！?？:：=＋+\-_()（）\[\]【】{}<>《》\"'“”‘’]+")
IMAGE_MATCH_SIZE_RE = re.compile(
    r"(?i)(?<!\d)(?:尺码|码数|鞋码|size)?\s*[:：=]?\s*(?:3[0-9]|4[0-9]|5[0-2])(?:\.5)?\s*(?:码|m|M)?(?!\d)"
)
IMAGE_MATCH_QTY_RE = re.compile(r"(?i)(?:x|×|\*)\s*\d+|\d+\s*(?:双|件|对)")


def normalize_image_match_text(value):
    text = normalize_match_text(value)
    for word in IMAGE_MATCH_NOISE_WORDS:
        marker = normalize_match_text(word)
        if marker:
            text = text.replace(marker, "")
    return text


def normalize_remark_match_text(value):
    text = str(value or "")
    text = IMAGE_MATCH_SIZE_RE.sub(" ", text)
    text = IMAGE_MATCH_QTY_RE.sub(" ", text)
    normalized = normalize_match_text(text)
    for word in IMAGE_MATCH_REMARK_WORDS:
        marker = normalize_match_text(word)
        if marker:
            normalized = normalized.replace(marker, "")
    return normalize_image_match_text(normalized)


def expand_image_match_aliases(text):
    variants = []

    def add(value):
        value = normalize_match_text(value)
        if value and value not in variants:
            variants.append(value)

    value = normalize_match_text(text)
    add(value)
    for current in list(variants):
        if "c6" in current:
            add(current.replace("c6", "cloud6"))
        if "cloud6" in current:
            add(current.replace("cloud6", "c6"))
        if "tilt" in current and "cloudtilt" not in current:
            add(current.replace("tilt", "cloudtilt"))
        if "cloudtilt" in current:
            add(current.replace("cloudtilt", "tilt"))

    for current in list(variants):
        for old, new in (("咖啡", "卡"), ("浅咖", "浅卡"), ("灰白色", "浅灰"), ("灰白", "浅灰")):
            if old in current:
                add(current.replace(old, new))
    return [v for v in variants if v]


def normalize_image_aliases(value):
    if isinstance(value, (list, tuple, set)):
        raw_parts = []
        for item in value:
            raw_parts.extend(re.split(r"[\n\r,，;；、/]+", str(item or "")))
    else:
        raw_parts = re.split(r"[\n\r,，;；、/]+", str(value or ""))

    aliases = []
    for part in raw_parts:
        alias = normalize_text(part)
        if alias and alias not in aliases:
            aliases.append(alias)
    return aliases


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
        aliases = [alias for alias in normalize_image_aliases(item.get("aliases", [])) if alias != spec]
        if aliases:
            item["aliases"] = aliases
        else:
            item.pop("aliases", None)
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


def upsert_image_binding(category, spec, source_path="", image_bytes=None, filename="image.png", aliases=None):
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
    key = make_image_key(category, spec)
    old_item = bucket.get(key, {}) if isinstance(bucket.get(key, {}), dict) else {}
    alias_list = normalize_image_aliases(old_item.get("aliases", []) if aliases is None else aliases)
    alias_list = [alias for alias in alias_list if alias != spec]
    bucket[make_image_key(category, spec)] = {
        "category": category,
        "spec": spec,
        "filename": os.path.basename(filename or source_path or "image.png"),
        "image_file": image_file
    }
    if alias_list:
        bucket[key]["aliases"] = alias_list
    save_image_category_map(category, bucket)
    return bucket[make_image_key(category, spec)]


def _stored_image_path(image_file):
    raw = str(image_file or "").strip()
    if not raw:
        return None
    try:
        if os.path.isabs(raw):
            candidate = Path(raw).resolve()
        else:
            candidate = (Path(get_data_dir()) / raw.replace("\\", os.sep)).resolve()
        images_dir = Path(get_images_dir()).resolve()
        if candidate.is_relative_to(images_dir):
            return candidate
    except Exception:
        return None
    return None


def referenced_image_paths():
    refs = set()
    for file in Path(get_image_category_dir()).glob("*.json"):
        try:
            data = json.loads(file.read_text(encoding="utf-8-sig"))
        except Exception:
            continue
        if not isinstance(data, dict):
            continue
        for item in data.values():
            if not isinstance(item, dict):
                continue
            path = _stored_image_path(item.get("image_file") or item.get("file"))
            if path:
                refs.add(str(path))
    return refs


def cleanup_unused_image_files(dry_run=False):
    image_dir = Path(get_images_dir()).resolve()
    refs = referenced_image_paths()
    stats = {
        "total": 0,
        "referenced": len(refs),
        "kept": 0,
        "deleted": 0,
        "would_delete": 0,
        "freed_bytes": 0,
        "files": [],
    }

    for file in image_dir.rglob("*"):
        if not file.is_file():
            continue
        stats["total"] += 1
        try:
            resolved = file.resolve()
        except Exception:
            continue
        if str(resolved) in refs:
            stats["kept"] += 1
            continue
        try:
            size = file.stat().st_size
            rel = str(resolved.relative_to(Path(get_data_dir()).resolve())).replace("\\", "/")
            if dry_run:
                stats["would_delete"] += 1
            else:
                file.unlink()
                stats["deleted"] += 1
            stats["freed_bytes"] += size
            stats["files"].append(rel)
        except Exception:
            continue

    if not dry_run:
        for folder in sorted((p for p in image_dir.rglob("*") if p.is_dir()), key=lambda p: len(p.parts), reverse=True):
            try:
                folder.rmdir()
            except OSError:
                pass

    return stats


def update_image_binding(old_category, old_spec, new_category, new_spec, aliases=None):
    old_category = normalize_text(old_category)
    old_spec = normalize_text(old_spec)
    new_category = normalize_text(new_category)
    new_spec = normalize_text(new_spec)
    if not old_category or not old_spec or not new_category or not new_spec:
        raise ValueError("分类和规格不能为空")

    old_bucket = load_image_category_map(old_category)
    old_key = make_image_key(old_category, old_spec)
    item = old_bucket.pop(old_key, None)
    if not isinstance(item, dict):
        raise ValueError("找不到要修改的图片关系")

    alias_list = normalize_image_aliases(aliases)
    alias_list = [alias for alias in alias_list if alias != new_spec]
    item["category"] = new_category
    item["spec"] = new_spec
    if alias_list:
        item["aliases"] = alias_list
    else:
        item.pop("aliases", None)

    save_image_category_map(old_category, old_bucket)
    new_bucket = load_image_category_map(new_category)
    new_bucket[make_image_key(new_category, new_spec)] = item
    save_image_category_map(new_category, new_bucket)
    return item


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
        marker = normalize_match_text(category_filter)
        matched = []
        for category in categories:
            category_marker = normalize_match_text(category)
            if normalize_text(category) == category_filter or category_marker == marker:
                matched.append(category)
            elif marker and len(marker) >= 2 and category_marker and (marker in category_marker or category_marker in marker):
                matched.append(category)
        categories = matched

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
            aliases = normalize_image_aliases(item.get("aliases", []))
            if keyword and keyword not in (cat + spec + "".join(aliases)):
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
        aliases = [alias for alias in normalize_image_aliases(item.get("aliases", [])) if alias != spec]
        if aliases:
            item["aliases"] = aliases
        else:
            item.pop("aliases", None)
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

    available = list_image_category_names()
    available_by_match = {}
    for name in available:
        marker = normalize_match_text(name)
        if marker:
            available_by_match.setdefault(marker, []).append(name)

    def matching_image_categories(category):
        result = []

        def add(value):
            value = normalize_text(value)
            if value and value not in result:
                result.append(value)

        add(category)
        marker = normalize_match_text(category)
        if marker:
            for value in available_by_match.get(marker, []):
                add(value)
            if len(marker) >= 2:
                for value in available:
                    value_marker = normalize_match_text(value)
                    if value_marker and (marker in value_marker or value_marker in marker):
                        add(value)
        return result

    merged = {}
    for category in categories_norm:
        for image_category in matching_image_categories(category):
            fp = _image_category_file(image_category)
            if not os.path.exists(fp):
                continue
            try:
                raw = Path(fp).read_text(encoding="utf-8-sig")
                data = json.loads(raw)
                if isinstance(data, dict):
                    for key, item in data.items():
                        if isinstance(item, dict):
                            cloned = dict(item)
                            cloned["category"] = category
                            spec = normalize_text(cloned.get("spec", ""))
                            merged[make_image_key(category, spec) if spec else key] = cloned
                        else:
                            merged[key] = item
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
        aliases = [alias for alias in normalize_image_aliases(item.get("aliases", [])) if alias != spec]
        if aliases:
            item["aliases"] = aliases
        else:
            item.pop("aliases", None)

        key = make_image_key(category, spec)
        by_key[key] = item
        for alias in item.get("aliases", []):
            by_key.setdefault(make_image_key(category, alias), item)
        by_category.setdefault(category, []).append(item)

    # 同分类下优先匹配更长规格，避免“黑”误命中“黑色加绒”
    for category, items in by_category.items():
        items.sort(
            key=lambda x: max(
                [len(normalize_text(x.get("spec", "")))]
                + [len(normalize_text(alias)) for alias in normalize_image_aliases(x.get("aliases", []))]
            ),
            reverse=True
        )

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

    def _match_variants(self, value, category=""):
        raw = normalize_match_text(value)
        clean = normalize_image_match_text(value)
        category_norm = normalize_match_text(category)
        variants = []
        for text in (raw, clean):
            if text and text not in variants:
                variants.append(text)
            if category_norm and text:
                stripped = text
                if stripped.startswith(category_norm):
                    stripped = stripped[len(category_norm):]
                elif stripped.endswith(category_norm):
                    stripped = stripped[:-len(category_norm)]
                if stripped and stripped not in variants:
                    variants.append(stripped)
                stripped_all = stripped.replace(category_norm, "")
                if stripped_all and stripped_all not in variants:
                    variants.append(stripped_all)

        for text in list(variants):
            if text.endswith("色") and len(text) >= 2:
                color_short = text[:-1]
                if color_short and color_short not in variants:
                    variants.append(color_short)
        for text in list(variants):
            for alias in expand_image_match_aliases(text):
                if alias not in variants:
                    variants.append(alias)
        return variants

    def _query_fragments(self, value):
        raw = str(value or "")
        fragments = []

        def add(text):
            compact = normalize_remark_match_text(text)
            if len(compact) >= 2 and compact not in fragments:
                fragments.append(compact)

        add(raw)
        no_size = IMAGE_MATCH_SIZE_RE.sub(" ", raw)
        no_qty = IMAGE_MATCH_QTY_RE.sub(" ", no_size)
        add(no_qty)

        parts = [p for p in IMAGE_MATCH_SPLIT_RE.split(no_qty) if p and p.strip()]
        for part in parts:
            add(part)
        for width in (2, 3):
            for idx in range(0, max(len(parts) - width + 1, 0)):
                add("".join(parts[idx:idx + width]))

        return fragments

    def _is_safe_containment(self, container, contained):
        if not container or not contained or contained not in container:
            return False
        extra = container.replace(contained, "", 1)
        return not normalize_image_match_text(extra)

    def _score_text_pair(self, item_spec, query_text, category=""):
        item_variants = self._match_variants(item_spec, category)
        query_variants = self._match_variants(query_text, category)

        if not item_variants or not query_variants:
            return 0

        best = 0
        for item_text in item_variants:
            for query_value in query_variants:
                if item_text == query_value:
                    best = max(best, 1000 + len(query_value))
                    continue

                if len(query_value) >= 3 and self._is_safe_containment(item_text, query_value):
                    best = max(best, 900 + len(query_value))

                if len(item_text) >= 3 and self._is_safe_containment(query_value, item_text):
                    best = max(best, 880 + len(item_text))

        return best

    def _candidate_specs(self, item):
        values = [normalize_text(item.get("spec", ""))]
        for alias in normalize_image_aliases(item.get("aliases", [])):
            if alias and alias not in values:
                values.append(alias)
        return values

    def _continuous_match(self, item_spec, query_text, category=""):
        return self._score_text_pair(item_spec, query_text, category) >= 880

    def find(self, category, spec, *extra_texts):
        category_norm = normalize_text(category)
        spec_norm = normalize_text(spec)
        query_texts = []
        for value in [spec_norm] + [x for x in extra_texts if normalize_text(x)]:
            for fragment in self._query_fragments(value):
                if fragment and fragment not in query_texts:
                    query_texts.append(fragment)
        cache_key = (category_norm, tuple(query_texts))

        if cache_key in self.cache:
            return self.cache[cache_key]

        exact_key = make_image_key(category_norm, spec_norm)
        item = self.by_key.get(exact_key)
        if item:
            self.cache[cache_key] = item
            return item

        candidates = self.by_category.get(category_norm, [])
        best_item = None
        best_score = 0
        best_spec_len = 10**9
        for candidate in candidates:
            item_specs = self._candidate_specs(candidate)

            if not item_specs:
                continue

            if spec_norm in item_specs:
                self.cache[cache_key] = candidate
                return candidate

            for query_text in query_texts:
                for item_spec in item_specs:
                    score = self._score_text_pair(item_spec, query_text, category_norm)
                    spec_len = len(normalize_match_text(item_spec))
                    if score > best_score or (score == best_score and score > 0 and spec_len < best_spec_len):
                        best_score = score
                        best_item = candidate
                        best_spec_len = spec_len

        if best_item and best_score >= 880:
            self.cache[cache_key] = best_item
            return best_item

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
        aliases = [alias for alias in normalize_image_aliases(item.get("aliases", [])) if alias != spec]
        if aliases:
            item["aliases"] = aliases
        else:
            item.pop("aliases", None)

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
            original_name = str(t.get("name", "")).strip()
            name = WAYBILL_TEMPLATE_NAME if original_name in LEGACY_RAW_WAYBILL_TEMPLATE_NAMES else original_name
            mode = str(t.get("mode", "表头") or "表头").strip()
            if name in REMOVED_IMPORT_TEMPLATE_NAMES or mode == RAW_WAYBILL_MODE:
                continue
            if not name or name in seen_templates:
                continue
            seen_templates.add(name)
            if name == WAYBILL_PROCESSED_TEMPLATE_NAME:
                t.update(WAYBILL_PROCESSED_IMPORT_TEMPLATE)
            elif mode == "表头":
                t.setdefault("short_name", "商品简称")
                t.setdefault("spec", "销售规格")
                t.setdefault("size", "")
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


def preview_data_summary(data=None, max_items=8, count_image_entries=True):
    if data is None:
        data = load_data()
    data = normalize_data(data)
    system, sid = get_active_system(data)

    templates = system.get("import_templates", [])
    rules = system.get("category_rules", [])
    stalls = system.get("stall_map", {})
    image_stats = image_storage_summary(count_entries=count_image_entries)
    image_categories = list_image_category_names()
    image_entries = image_stats.get("entries")
    if image_entries is None:
        image_entries = image_stats.get("image_files", 0)

    return {
        "system_id": sid,
        "system_name": system.get("name", sid),
        "templates_count": len(templates),
        "rules_count": len(rules),
        "stalls_count": len(stalls),
        "images_count": image_entries or 0,
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
