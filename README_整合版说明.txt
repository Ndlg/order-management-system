订单整理系统 - Web + 本地整合版

本项目包含：
- 后端数据管理
- 本地前端订单整理
- Web控制台
- Web前端页面
- 统一核心整理模块 order_core.py

核心优化：
原来规则越多越慢，是因为每条订单都重复遍历全部规则。
现在把规则预处理到 RuleEngine 中，本地和Web共用 order_core.py，避免版本逻辑不一致。

安装依赖：
python -m pip install pandas openpyxl pillow cryptography fastapi uvicorn python-multipart pyinstaller

编译后端：
python -m PyInstaller -F -w -n 后端数据管理 ^
--icon=icon_backend.ico ^
--add-data "icon_backend.ico;." ^
--add-data "icon_backend.png;." ^
--hidden-import=order_secure_common ^
--collect-all PIL ^
--collect-all cryptography ^
order_backend_admin.py

编译本地前端：
python -m PyInstaller -F -w -n 前端订单整理 ^
--icon=icon_frontend.ico ^
--add-data "icon_frontend.ico;." ^
--add-data "icon_frontend.png;." ^
--hidden-import=order_secure_common ^
--hidden-import=order_core ^
--collect-all PIL ^
--collect-all cryptography ^
order_frontend.py

编译Web控制台：
python -m PyInstaller -F -w -n 订单整理Web控制台 ^
--icon=icon_web.ico ^
--add-data "icon_web.ico;." ^
--add-data "icon_web.png;." ^
--add-data "templates;templates" ^
--hidden-import=app ^
--hidden-import=order_secure_common ^
--hidden-import=order_core ^
--collect-all fastapi ^
--collect-all starlette ^
--collect-all uvicorn ^
--collect-all PIL ^
--collect-all cryptography ^
web_launcher.py


v2调整：
1. 后端删除“当前模板”控制，后端只维护模板。
2. 本地前端选择模板后生成。
3. Web前端选择模板后生成。
4. 三个EXE分别使用不同图标：
   - 后端数据管理：icon_backend.ico
   - 前端订单整理：icon_frontend.ico
   - Web控制台：icon_web.ico
