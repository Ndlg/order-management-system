# SKU图片批量绑定工具

目标：把淘宝/抖音等店铺里已经合法导出的 SKU 表、图片链接或本地图片包，批量写入系统现有图片库，减少一张张手工绑定。

## 推荐流程

1. 先生成模板：

```bat
python src/utils/sku_image_binder.py template
```

模板会写到 `C:\myproject\output\SKU图片绑定模板_*.xlsx`。

2. 把店铺导出的数据整理成这些列：

- `鞋款`：系统里的图片分类，例如 `昂跑`、`ACG`、`5.0`
- `规格`：订单里会出现的 SKU/颜色/规格，例如 `Cloudtilt白黑`
- `图片路径`：本地图片路径，可以是完整路径，也可以只是文件名
- `图片链接`：如果没有本地图片，可以填图片 URL
- `别名`：同一 SKU 的其他写法，用 `；` 分隔

3. 先预览，不写入：

```bat
python src/utils/sku_image_binder.py import C:\myproject\output\SKU图片绑定模板_20260602_120000.xlsx --image-dir D:\店铺图片 --dry-run
```

4. 确认报告无误后正式导入：

```bat
python src/utils/sku_image_binder.py import C:\myproject\output\SKU图片绑定模板_20260602_120000.xlsx --image-dir D:\店铺图片
```

正式导入前会备份 `C:\myproject\data\image_categories`，图片会按内容哈希去重保存到 `C:\myproject\data\images`。

## 生成缺图清单

对订单整理文件或面单识别结果生成“还没绑定图片”的 SKU 清单：

```bat
python src/utils/sku_image_binder.py missing C:\myproject\output\监控面单识别_那道蓝光.xlsx
```

如果表里没有鞋款列，但整张表都属于同一个鞋款：

```bat
python src/utils/sku_image_binder.py missing D:\订单.xlsx --default-category 昂跑
```

## 边界

工具不会自动登录淘宝/抖音，也不会绕过验证码或风控。它只处理你已经能导出的表格、复制出的图片链接、或下载到本地的图片目录。
