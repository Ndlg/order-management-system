# 业务机采集助手发布策略

从 V7.9.3 开始，每次订单整理系统发布新版本时，都必须声明业务机采集助手版本状态。

## 需要重新构建采集助手的情况

- `src/plugins/collector_agent/` 代码发生变化。
- Web 上传协议或 poll 指令字段发生不兼容变化。
- 存在严重漏采风险。
- 旧版本无法识别或回传 task_id / component_rowid。
- 旧版本存在数据丢失缺陷。

重新构建时，版本目录必须包含：

- `versions/vX.Y.Z/bin/OrderCollectorAgent_vX.Y.Z.exe`
- `versions/vX.Y.Z/bin/OrderCollectorAgent_vX.Y.Z.zip`
- `versions/vX.Y.Z/release_manifest.json`
- `versions/vX.Y.Z/tests/report.log`

## 不需要重新构建采集助手的情况

如果主系统升级但采集助手代码和协议没有变化，可以不重新打包业务机 EXE，但必须在 `release_manifest.json` 中记录兼容的采集助手版本，并在版本说明中写明业务机无需升级。

## 协议字段

采集助手上报：

- `agent_version`
- `protocol_version`
- `client_id`
- `machine_name`
- `machine_label`
- `component_status`
- `last_seen`

服务端返回：

- `server_version`
- `protocol_version`
- `min_supported_agent_version`
- `latest_agent_version`
- `upgrade_required`
- `upgrade_message`
- `download_url`
