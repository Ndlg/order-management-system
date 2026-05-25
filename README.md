# 订单整理管理系统

当前版本：`V7.5.1-LiteData-20260525`

## 本版重点

1. 启动加载页改为真实阶段进度，显示主数据大小、解密解析、图片分片扫描结果。
2. 主数据 `system_data.enc` 改为轻量结构，只保存模板、规则、档口和用户。
3. 图片关系改为 `data/image_categories/*.json` 分类分片存储，图片文件按哈希存到 `data/images/`。
4. 保存图片、批量导入图片不再重写巨型主库，后续整理订单只按实际用到的分类懒加载图片关系。
5. 保留 V7.4.8 的备注匹配、连续规格匹配、Web 客户端 zip 下载能力。

## 目录说明

- `order_backend_admin.py`：后台数据管理。
- `order_frontend.py`：一键整理订单桌面端。
- `web_launcher.py`：Web 服务控制台。
- `app.py`：FastAPI Web 后端。
- `order_core.py`：订单整理共享核心。
- `order_secure_common.py`：数据、模板、图片索引和安全存储公共逻辑。
- `templates/`：Web 页面模板。
- `requirements.txt`：运行和编译依赖。
- `一键编译全部.bat`：编译三个 EXE。

## 运行源码

```bat
python order_backend_admin.py
python order_frontend.py
python web_launcher.py
```

## 编译

```bat
一键编译全部.bat
```

编译产物会生成到 `dist/`。`data/`、`output/`、`temp/`、`dist/`、`build/` 都是运行或构建产物，不纳入 Git 源码管理。

V7.5.1 是轻量数据结构新线，默认不携带旧版数据。旧版大 `system_data.enc` 不建议直接放入本版本使用。
