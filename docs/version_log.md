# 版本记录

## v7.9.2 - 2026-06-06
- 目录: 当前 main 已整理为规范目录结构。
- 说明: 以 `V7.9.2_20260605` 当前使用版本作为整理基线。

## v7.9.2 - 2026-06-06
- 目录: `src/core`, `src/ui`, `src/utils`
- 说明: 主程序代码已按核心逻辑、界面、通用工具真实拆分存储。

## v7.9.2 - 2026-06-06 23:09:24
- 目录: `C:/Users/ndlgx/Documents/Projects/GitHub/Ndlg/order-management-system/versions/v7.9.2`
- 拉取源码: skipped
- 回归测试: 通过 (0)
- 产物: OrderSystem_source_v7.9.2.zip

## v7.9.2 - 2026-06-06 23:56:31
- 目录: `C:/Users/ndlgx/Documents/Projects/GitHub/Ndlg/order-management-system/versions/v7.9.2`
- 拉取源码: skipped
- 回归测试: 通过 (0)
- 产物: OrderSystem_source_v7.9.2.zip, Web服务控制台.exe, 一键整理订单.exe, 订单整理管理系统.exe, OrderSystem_v7.9.2.zip

## v7.9.3 - 2026-06-07 00:38:11
- 目录: `C:/Users/ndlgx/Documents/Projects/GitHub/Ndlg/order-management-system/versions/v7.9.3`
- 拉取源码: skipped
- 回归测试: 通过 (0)
- 产物: OrderSystem_source_v7.9.3.zip, Web服务控制台.exe, 一键整理订单.exe, 订单整理管理系统.exe, OrderSystem_v7.9.3.zip

# v7.9.3 - 2026-06-07

- 重构业务机采集端为官方 `OrderCollectorAgent`，源码放入 `src/plugins/collector_agent/`。
- 删除旧独立采集客户端方案和旧采集模式代码。
- 新增 `/api/collector/*` 绑定、轮询、上传、业务机列表、原文记录和版本接口。
- 采集助手不做识别、不做筛选，不区分采集模式。
- 构建流程新增 `--build-agent` 和 `release_manifest.json`。
## v7.9.3 - 2026-06-07 01:53:57
- 目录: `C:/Users/ndlgx/Documents/Projects/GitHub/Ndlg/order-management-system/versions/v7.9.3`
- 拉取源码: skipped
- 回归测试: 通过 (0)
- 产物: OrderSystem_source_v7.9.3.zip, Web服务控制台.exe, 一键整理订单.exe, 订单整理管理系统.exe, OrderSystem_v7.9.3.zip, OrderCollectorAgent_v7.9.3.exe, OrderCollectorAgent_v7.9.3.zip, release_manifest.json

## v7.9.3 - 2026-06-07 02:02:10
- 目录: `C:/Users/ndlgx/Documents/Projects/GitHub/Ndlg/order-management-system/versions/v7.9.3`
- 拉取源码: skipped
- 回归测试: 通过 (0)
- 产物: OrderSystem_source_v7.9.3.zip, OrderCollectorAgent_v7.9.3.exe, OrderCollectorAgent_v7.9.3.zip, release_manifest.json

