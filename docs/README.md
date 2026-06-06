# 订单整理管理系统

当前版本：`V7.9.2_20260605`

项目目录、模块边界和构建入口见 [`assembly_overview.md`](assembly_overview.md)。

## 本版目标

V7.8.3 新增管理端 `面单解析` 工作台：可以直接打开采集到的原始 Excel，先按系统规则自动识别，再在表格中手动修正，最后导出识别后的 Excel。

## 监听打印机版基础

V7.8.2 是在 V7.8.1 监听打印机版基础上补齐“原始文档 + 识别文档 + 自动导入识别文档”的版本。采集工具只回传打印信息原文，订单系统收到原始文件后再独立识别五个要素：

- `鞋款`
- `规格`
- `尺码`
- `数量`
- `备注`

后续所有模块都只消费这五个标准字段，不再直接拿原始长标题、店铺代号或混合规格做最终判断。

## 监听打印机版新增

- Web 生成页保留 `监听打印机面单` 区块。
- 业务机采集客户端只负责回传原文，源码已移入 `scripts/collector_client_legacy/`，不属于当前主发布包。
- Web 点击 `开始监听` 后，业务机记录当前打印任务为基准。
- Web 点击 `结束监听并加入待处理` 后，业务机只上传本次新打印信息。
- 服务端生成 `监控面单原文_*.xlsx`，固定表头只有 `打印信息`。
- 面单监控工具不识别鞋款、规格、尺码、数量或备注。
- 生成整理文档时自动使用系统模板 `监控面单-原文模式`，由订单系统解析原文并进入现有整理流程。
- 解析后的中间文件格式后续再定；当前代码已把解析管线独立到系统侧。

## 主流程

1. `src/core/five_field_normalizer.py`：把不同来源模板识别为五要素。
2. `鞋款分类`：把五要素里的 `鞋款` 归入系统鞋款分类。
3. `鞋款档口`：维护鞋款分类与档口的绑定关系。
4. `图片关系`：维护鞋款分类下的规格与图片绑定。
5. `输出整理文档`：按档口、鞋款、规格合并尺码和数量。

## 开发边界

- 当前源码目录：`src/`
- V7.7.1 现在视为旧版本修复线，不再承载新架构大改。
- Qt 编译临时目录：`tmp/build/dist_qt_vX_Y_Z_YYYYMMDD_HHMMSS`。
- 系统发布包只包含管理系统、一键整理订单、Web服务控制台。
- 本地数据目录：`data/`。
- 本地输出目录：`data/output/`。
- 数据内部暂时保留 `category_rules`、`stall_map` 兼容键；界面和后续开发语义按 `鞋款分类`、`鞋款档口` 理解。

## 入口文件

- `src/core/five_field_normalizer.py`：五要素识别与标准行模块。
- `src/core/order_core.py`：订单整理核心逻辑。
- `src/core/waybill_files.py`：服务端面单批次文件命名、原文 Excel 写出和记录去重。
- `src/core/waybill_collector_reader.py`：业务机打印组件数据库读取。
- `src/core/waybill_monitor.py`：旧兼容入口，新代码不再直接依赖。
- `src/core/waybill_raw_contract.py`：面单原文模板、字段和内部管线字段契约。
- `src/core/waybill_raw_pipeline.py`：订单系统侧的打印信息原文解析管线。
- `src/ui/app.py`：FastAPI Web 后端。
- `src/ui/qt_admin.py`：订单整理管理系统。
- `src/ui/qt_client.py`：一键整理订单客户端。
- `src/ui/qt_web_console.py`：Web 服务控制台。
- `src/utils/app_info.py`：版本信息。
- `src/utils/order_secure_common.py`：数据、模板、图片、路径和兼容迁移工具。
- `src/utils/sku_image_binder.py`：SKU 图片批量绑定工具。
- `scripts/collector_client_legacy/`：旧业务机独立采集客户端源码，当前发布包不附带，主系统 Qt 打包也不强制包含。
- `scripts/build_qt_windows.py`：Qt 版本编译入口。
- `scripts/build_version.py`：规范版本目录生成入口。

## 运行

```bat
python src/ui/qt_admin.py
python src/ui/qt_client.py
python src/ui/qt_web_console.py
```

## 编译

```bat
python scripts/build_qt_windows.py
python scripts/build_version.py 7.9.2
```

旧业务机采集客户端仅保留在 `scripts/collector_client_legacy/`，当前系统发布包不再附带。
