# 项目规范

## 目录结构

- `src/`: 主程序源码。
- `src/core/`: 核心逻辑，包含订单解析、合并、统计、面单解析和文件输出。
- `src/ui/`: 前端界面，包含 FastAPI Web、Qt 入口、Qt 共用组件和 UI 资源。
- `src/utils/`: 工具函数和通用模块，包含版本信息、数据存储、安全兼容和 SKU 图片工具。
- `src/tests/`: 单元测试和回归测试。
- `src/` 根目录不存放业务 `.py` 文件，只保留子包目录。
- `data/input/`: 原始订单文件、图片等输入数据，禁止直接修改。
- `data/reference/`: 共用参考数据，例如尺码表、鞋款映射表、SKU 关系表。
- `data/output/`: 系统生成输出目录。
- `data/` 根目录也承载本地生产数据，例如 `system_data.enc`、`import_templates.json`、`images/`、`image_categories/`，供项目内生成的 exe 共用。
- `versions/vX.Y.Z/`: 每个新版本的唯一产物目录。
- `docs/`: 说明书、版本说明、规范。
- `scripts/`: 构建、迁移、清理等辅助脚本。
- `tmp/`: 临时文件目录。

## 版本生成

版本号遵循 `主版本.次版本.修订号`，例如 `7.5.1`。

生成版本：

```powershell
python scripts/build_version.py 7.5.1
```

生成目录：

```text
versions/v7.5.1/
├── bin/
├── logs/
├── source/
└── tests/
```

目录规则：

- `bin/`: 只放生产交付物，例如 `OrderSystem_vX.Y.Z.exe` 或只包含 exe 的 `OrderSystem_vX.Y.Z.zip`。
- `source/`: 只放当代源码快照，例如 `OrderSystem_source_vX.Y.Z.zip`，用于回溯和审计，不作为生产交付物。
- `logs/`: 构建日志。
- `tests/`: 回归测试数据副本和报告。

默认会生成源码快照和测试报告，不生成 exe。如需尝试 PyInstaller 打包：

```powershell
python scripts/build_version.py 7.5.1 --build-exe
```

生成后的处理规则：

- 给实际使用的人，只拿 `versions/vX.Y.Z/bin/` 里的 exe 或 release zip。
- 源码不放进生产交付包；源码以 GitHub main 和 `versions/vX.Y.Z/source/` 快照为准。
- 生产数据不打包进 exe，也不放进 release zip；exe 在项目内运行时共用项目根目录 `data/`。

## 测试和输出

- 新版本测试数据会从 `data/input/` 和 `data/reference/` 复制到 `versions/vX.Y.Z/tests/`。
- 回归测试报告写入 `versions/vX.Y.Z/tests/report.log`。
- 构建日志写入 `versions/vX.Y.Z/logs/YYYYMMDD_HHMMSS.log`。
- 临时文件统一进入 `tmp/` 或版本目录，不能散落在根目录。
