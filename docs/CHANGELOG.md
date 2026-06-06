# 更新记录

## V7.9.3

- 删除旧的独立业务机采集客户端方案。
- 新增官方采集助手源码目录 `src/plugins/collector_agent/`。
- 新增采集助手后端持久化模块 `src/core/collector_agent_store.py`。
- 新增 `/api/collector/bind-code`、`/api/collector/bind`、`/api/collector/poll`、`/api/collector/upload`、`/api/collector/agents`、`/api/collector/records`、`/api/collector/version-info`。
- Web 页面新增业务机绑定码、在线状态、agent/protocol 版本、升级状态和打印原文查看。
- 采集助手不再区分采集模式，不在业务机端做识别或筛选。
- 每个进入批次范围的 `component_rowid` 至少上传一条原文记录。
- 上传失败会写入业务机本地 pending 队列，恢复连接后重试。
- 新增 `scripts/build_collector_agent.py`。
- `scripts/build_version.py --build-agent` 会生成采集助手产物和 `release_manifest.json`。
- 新增采集助手专项测试，覆盖 rowid 不丢失、异常回退、鉴权、重复上传和 pending 队列。
