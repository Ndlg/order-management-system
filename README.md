# 订单整理管理系统

订单整理、模板配置、报货导出与数据管理工具。

## 版本

当前上传版本：V7.4.7 稳定版

## 主要功能

- 订单数据整理
- 模板配置管理
- 报货导出
- Web 控制台
- 前后端分离启动入口
- 分类图片懒加载优化

## 运行方式

```bash
pip install -r requirements.txt
python app.py
```

Windows 环境可以使用项目内 `.bat` 脚本启动或编译。

## 主要文件

- `app.py`：Web 控制台入口
- `order_core.py`：订单整理核心逻辑
- `order_frontend.py`：前端入口
- `order_backend_admin.py`：后端管理入口
- `order_secure_common.py`：公共安全/工具模块
- `web_launcher.py`：Web 启动器
- `templates/index.html`：Web 页面模板
- `requirements.txt`：Python 依赖

## 维护建议

本仓库保存稳定版源码。后续迭代建议使用独立分支开发，并通过 Pull Request 合并。