V7.5 修复说明

问题：
Web 页面已经显示 V7.4 版本，但生成时仍报：
name 'ImageMatcher' is not defined

原因：
app.py 内部存在 ImageMatcher 调用，但 order_secure_common 的导入列表没有真正包含 ImageMatcher。
之前的自动修复脚本用全文判断，误判已经导入。

处理：
1. 强制重写 app.py 的 order_secure_common 导入块。
2. 明确加入 ImageMatcher。
3. 明确加入 get_data_dir。
4. 保持 /api/generate 统一调用 order_core.generate_order_file。
5. Web版本号升级为 V7.5-WebImportFix-20260512。

验证：
打开 Web 页面应显示：
Web后端版本：V7.5-WebImportFix-20260512
