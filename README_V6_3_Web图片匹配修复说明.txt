V6.3 修复说明

修复 Web 端生成整理文档时报错：
name 'ImageMatcher' is not defined

原因：
Web 服务 app.py 的图片匹配逻辑已切换为 ImageMatcher，但导入列表缺少 ImageMatcher。

处理：
已补齐 app.py 中 order_secure_common 的 ImageMatcher 导入。
