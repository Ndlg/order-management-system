# 业务机采集助手使用说明

工具名称：订单整理系统 - 业务机采集助手  
内部名称：`OrderCollectorAgent`  
当前版本：7.9.3

## 用途

采集助手安装在业务机上，用来读取本机打印组件数据库，并把打印任务原始信息回传到订单整理系统 Web 后端。它不识别订单字段、不筛选、不合并、不生成 Excel。

## 绑定流程

1. 在 Web 页面“监听打印机面单”区域点击“生成绑定码”。
2. 在业务机打开采集助手，填写 Web 服务器地址和绑定码。
3. 点击“连接/重新绑定”。
4. Web 页面会显示业务机在线状态、组件状态、agent_version、protocol_version 和最近上传信息。

## 日常使用

1. Web 页面点击“开始监听”。
2. 业务机采集助手 poll 到 `start` 指令后记录本机打印组件当前最大 rowid 作为 baseline。
3. 业务机正常打印面单。
4. Web 页面点击“结束监听并加入待处理”。
5. 采集助手上传 baseline 之后新增的每一条打印任务原文。
6. Web 页面可查看打印原文、task_id、document_id、component_rowid 和异常状态。

## 本地目录

- 配置：`C:\ProgramData\OrderSystemCollector\config\`
- 日志：`C:\ProgramData\OrderSystemCollector\logs\`
- 缓存：`C:\ProgramData\OrderSystemCollector\cache\`
- 待重试：`C:\ProgramData\OrderSystemCollector\pending_uploads\`

上传失败时，记录会进入 `pending_uploads`，恢复连接后自动重试。
