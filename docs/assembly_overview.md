# 代码组装说明

## 模块边界

- `src/core/`: 订单整理核心、五要素解析、鞋款规则、面单解析、面单文件输出。
- `src/ui/`: FastAPI Web 服务、Qt 管理端、Qt 客户端、Web 控制台、UI 模板和图标资源。
- `src/utils/`: 版本信息、数据存储、加密兼容、图片绑定和通用路径工具。
- `scripts/`: 构建、版本生成、旧采集器打包脚本。

## 运行入口

```powershell
$env:PYTHONPATH = "$PWD/src"
python src/ui/qt_admin.py
python src/ui/qt_client.py
python src/ui/qt_web_console.py
uvicorn ui.app:app --app-dir src --host 127.0.0.1 --port 8000
```

## 构建入口

```powershell
python scripts/build_version.py 7.9.2
python scripts/build_version.py 7.9.2 --build-exe
```

生成内容只允许进入 `versions/vX.Y.Z/`，临时文件只允许进入 `tmp/` 或版本目录。

版本目录处理规则：

- `versions/vX.Y.Z/bin/`: 生产交付目录，只放 exe 和只包含 exe 的 release zip。
- `versions/vX.Y.Z/source/`: 源码快照目录，只用于回溯，不给生产使用者。
- `versions/vX.Y.Z/tests/`: 测试数据副本和 `report.log`。
- `versions/vX.Y.Z/logs/`: 构建日志。

实际发给使用者时，只取 `bin/`。源码以 GitHub main 和 `source/` 快照保留，不混入 exe 交付包。

编译完成后可运行无界面自检：

```powershell
versions/v7.9.2/bin/订单整理管理系统.exe --self-test
versions/v7.9.2/bin/一键整理订单.exe --self-test
versions/v7.9.2/bin/Web服务控制台.exe --self-test
```

## 共用数据

项目本地运行数据放在 `data/`。这里会保存 `system_data.enc`、`import_templates.json`、`images/`、`image_categories/`、`waybill-monitor/` 等生产数据。

这些数据体积大且可能包含业务资料，默认被 `.gitignore` 忽略，不推到 GitHub。只要 exe 保持在项目目录或 `versions/vX.Y.Z/bin/` 下运行，程序会向上查找项目根目录并共用 `data/`。

如需把 exe 拷贝到项目外运行，可以设置环境变量：

```powershell
$env:ORDER_SORTER_DATA_DIR = "C:\path\to\order-management-system\data"
```

## 自动检查

回归测试会检查：

- 尺码数量统计。
- 图片嵌入冒烟。
- 面单解析空批次。
- 输出目录遵守 `data/output/`。
- `src/` 根目录不允许散落业务 `.py` 文件。
- 代码不允许继续使用旧平铺导入。
