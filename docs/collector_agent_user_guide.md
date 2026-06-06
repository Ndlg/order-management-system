# 业务机采集助手使用说明

工具名称：订单整理系统 - 业务机采集助手  
内部名称：`OrderCollectorAgent`  
当前版本：7.9.3

## 用途

采集助手安装在业务机上，用来读取本机打印组件数据库，并把打印任务原始信息回传到订单整理系统 Web 后端。它不识别订单字段、不筛选、不合并、不生成 Excel。

## 上线注册

1. 在业务机打开采集助手，进入“打开设置”。
2. 填写 Web 服务器地址和业务机名称后保存。
3. 采集助手会自动上线注册，并进入后台心跳轮询。
4. Web 页面会显示业务机在线状态、组件状态、agent_version、protocol_version 和最近上传信息。

## 日常使用

1. Web 页面点击“开始监听”。
2. 业务机采集助手 poll 到 `start` 指令后记录本机打印组件当前最大 rowid 作为 baseline。
3. 业务机正常打印面单。
4. Web 页面点击“结束监听并加入待处理”。
5. 采集助手上传 baseline 之后新增的每一条打印任务原文。
6. Web 页面可查看打印原文、task_id、document_id、component_rowid 和异常状态。

## 后台常驻

- 采集助手只能单开，已经运行时再次打开会提示已在运行。
- 采集助手启动后会自动建立心跳轮询。
- 当前没有业务任务时，主界面显示“已连接 / 待命 / 等待任务”。
- Web 服务暂时不可达时，主界面显示“重连中”，并按固定间隔自动重试。
- Web 服务恢复后，采集助手会自动回到“已连接 / 待命”。
- 点击“停止服务”后会保持“服务已停止 / 已停止”，不会被后台残留心跳覆盖成“重连中”。
- 关闭主窗口不会退出程序，采集助手会最小化到系统托盘继续运行。
- 托盘菜单支持打开主界面、查看当前状态、立即重连、查看日志、切换开机启动和退出程序。
- 开机启动会以最小化到托盘的方式运行。

## 本地目录

- 配置：`C:\ProgramData\OrderSystemCollector\config\`
- 日志：`C:\ProgramData\OrderSystemCollector\logs\`
- 缓存：`C:\ProgramData\OrderSystemCollector\cache\`
- 待重试：`C:\ProgramData\OrderSystemCollector\pending_uploads\`

上传失败时，记录会进入 `pending_uploads`，恢复连接后自动重试。
