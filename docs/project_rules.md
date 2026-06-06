# 项目规范

## 目录结构

- `src/`: 主程序源码。
- `src/core/`: 核心逻辑预留目录，后续拆分订单解析、合并、统计模块。
- `src/ui/`: 前端界面预留目录。
- `src/utils/`: 工具函数和通用模块预留目录。
- `src/tests/`: 单元测试和回归测试。
- `data/input/`: 原始订单文件、图片等输入数据，禁止直接修改。
- `data/reference/`: 共用参考数据，例如尺码表、鞋款映射表、SKU 关系表。
- `data/output/`: 系统生成输出目录。
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
└── tests/
```

默认产物是 `OrderSystem_vX.Y.Z.zip`。如需尝试 PyInstaller 打包：

```powershell
python scripts/build_version.py 7.5.1 --build-exe
```

## 测试和输出

- 新版本测试数据会从 `data/input/` 和 `data/reference/` 复制到 `versions/vX.Y.Z/tests/`。
- 回归测试报告写入 `versions/vX.Y.Z/tests/report.log`。
- 构建日志写入 `versions/vX.Y.Z/logs/YYYYMMDD_HHMMSS.log`。
- 临时文件统一进入 `tmp/` 或版本目录，不能散落在根目录。
