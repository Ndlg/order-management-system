当前版本：V7.4.2-debug

这是诊断测试版，不作为最终稳定版。

新增接口：
- /api/version
- /api/self-check
- /api/debug/core-check

生成失败时会返回完整 traceback 和模块路径。
请先打开 /api/self-check，如果 ok=false，把页面内容发回。
