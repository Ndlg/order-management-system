V7.2 修复说明

修复 Web 版本生成时报错：
name 'ImageMatcher' is not defined

处理方式：
1. 补齐 Web 服务 app.py 的 ImageMatcher / get_data_dir 导入。
2. Web 端 /api/generate 接口统一调用 order_core.generate_order_file。
3. 避免 app.py 内部旧整理逻辑与本地“一键整理订单”逻辑分叉。

注意：
更新后需要重新编译 web服务控制台.exe，或者直接用 python web_launcher.py 测试源码版。
浏览器页面如果仍显示旧错误，请重启 web服务控制台并刷新页面。
