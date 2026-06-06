# 项目规范

## 目录结构

- `src/`：主程序源码。
- `src/core/`：核心逻辑，包括订单解析、合并、统计、面单解析和采集助手后端存储。
- `src/ui/`：前端界面，包括 FastAPI Web、Qt 入口、Qt 公共组件和 UI 资源。
- `src/plugins/collector_agent/`：官方业务机采集助手 `OrderCollectorAgent` 源码。
- `src/utils/`：工具函数和通用模块。
- `src/tests/`：单元测试和回归测试。
- `data/input/`：原始订单文件、图片、采集样本等输入数据，禁止直接修改生产原件。
- `data/reference/`：共用参考数据，例如尺码表、鞋款映射表、SKU 关系表、采集样本。
- `data/output/`：系统生成输出目录。
- `versions/vX.Y.Z/`：每个新版本的唯一产物目录。
- `docs/`：说明书、版本说明、规范和需求任务书。
- `scripts/`：构建、迁移、清理等辅助脚本。
- `tmp/`：临时文件目录。

## 版本生成

版本号遵循 `主版本.次版本.修订号`，例如 `7.9.3`。

```powershell
python scripts/build_version.py 7.9.3 --build-exe --build-agent
```

版本目录：

```text
versions/v7.9.3/
├── bin/
├── logs/
├── source/
├── tests/
└── release_manifest.json
```

规则：

- 所有版本产物必须进入 `versions/vX.Y.Z/`。
- `bin/` 只放生产交付物，例如主系统 EXE、`OrderSystem_vX.Y.Z.zip`、`OrderCollectorAgent_vX.Y.Z.exe`、`OrderCollectorAgent_vX.Y.Z.zip`。
- `source/` 只放源码快照，用于回溯和审计，不作为业务机交付包。
- `logs/` 写入 `YYYYMMDD_HHMMSS.log`。
- `tests/` 写入测试数据副本和 `report.log`。
- `release_manifest.json` 必须声明主系统版本、采集助手版本、协议版本和业务机是否需要升级。
- 临时文件只能放到 `tmp/` 或版本目录，构建结束后应清理中间目录。

## 业务机采集助手规则

- 官方名称：订单整理系统 - 业务机采集助手。
- 内部名称：`OrderCollectorAgent`。
- 源码位置：`src/plugins/collector_agent/`。
- 运行位置：业务机独立 EXE / 后台采集服务 / 简易界面。
- 业务机交付物：只发 `OrderCollectorAgent_vX.Y.Z.zip` 或对应安装包。
- 不得把源码、测试数据、生产 `data/` 打包给业务机。
- 采集助手不做识别、不做筛选、不区分采集模式、不生成整理 Excel。
- 每个进入批次范围的 `component_rowid` 至少上传一条记录。
- 上传失败必须进入本地 pending 队列，服务端确认 accepted 后才允许更新游标。

## 数据和输出

- `data/input/` 和 `data/reference/` 是测试和固定参考数据。
- `data/output/` 是运行输出目录。
- 生产数据可在项目根目录 `data/` 下被 exe 共用，但不得打包进业务机采集助手。
- Codex 输出的临时文件不得散落在根目录。
