# 订单整理系统说明

当前版本：V7.9.3

V7.9.3 将业务机采集端重构为官方配套工具 `OrderCollectorAgent`。采集助手只部署在业务机上读取本机打印组件数据库，并把原始打印任务完整回传到 Web 后端；它不做面单识别、不做筛选、不维护鞋款规则，也不生成整理 Excel。

## 目录结构

- `src/core/`：订单整理、面单原文解析、采集助手后端持久化等核心逻辑。
- `src/ui/`：FastAPI Web、Qt 入口、Web 模板和界面资源。
- `src/plugins/collector_agent/`：官方业务机采集助手源码。
- `src/tests/`：单元测试与回归测试。
- `data/input/`：原始测试输入，禁止直接改写生产原件。
- `data/reference/`：尺码表、鞋款映射、采集样本等参考数据。
- `data/output/`：系统运行输出目录。
- `versions/vX.Y.Z/`：每个版本唯一产物目录。
- `docs/`：项目说明、版本说明、需求任务书。
- `scripts/`：构建、迁移和清理脚本。
- `tmp/`：临时构建和测试中间文件。

## 业务机采集助手

源码位置：`src/plugins/collector_agent/`

运行定位：业务机独立轻量 EXE / 后台采集服务 / 简易界面。业务机只需要拿 `versions/vX.Y.Z/bin/OrderCollectorAgent_vX.Y.Z.zip` 或对应 EXE，不需要源码目录、测试数据或生产数据。

核心规则：

- 每个进入批次范围的打印组件 `task.rowid` 至少生成一条上传记录。
- 不因为 JSON 解析失败、documents 为空、printXML 失败、空文本、重复文本或重复 task_id 丢弃记录。
- 上传前不做订单字段识别、不做筛选、不做合并。
- 上传失败时写入业务机本地 `pending_uploads`，恢复连接后继续重试。

业务机运行目录：

- `C:\ProgramData\OrderSystemCollector\config\`
- `C:\ProgramData\OrderSystemCollector\logs\`
- `C:\ProgramData\OrderSystemCollector\cache\`
- `C:\ProgramData\OrderSystemCollector\pending_uploads\`

## Web 接口

采集助手主接口统一使用 `/api/collector/*`：

- `POST /api/collector/bind-code`
- `POST /api/collector/bind`
- `POST /api/collector/poll`
- `POST /api/collector/upload`
- `GET /api/collector/agents`
- `GET /api/collector/records`
- `GET /api/collector/version-info`

旧的 Web“开始监听 / 结束监听”按钮仍可使用，它们会通过新 poll 指令驱动业务机采集助手。

## 构建

生成完整版本目录：

```powershell
python scripts/build_version.py 7.9.3 --build-exe --build-agent
```

只构建业务机采集助手：

```powershell
python scripts/build_collector_agent.py --version 7.9.3 --output-dir versions/v7.9.3/bin
```

交付给实际使用者时，只拿 `versions/vX.Y.Z/bin/` 里的 EXE 或 zip。源码快照只用于回溯和审计，不放进生产交付包。生产数据不打包进 EXE，也不提交到 GitHub。
