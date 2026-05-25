V7.4 Web版本标识说明

版本号：
V7.4-WebCore-20260512-ImageMatcherFix

新增：
1. Web页面顶部显示“Web后端版本”。
2. /api/status 返回 web_version。
3. /api/version 返回 web_version。
4. 生成成功或失败时也返回 web_version。
5. web服务控制台窗口标题显示版本号。

验证方式：
打开浏览器访问：
http://127.0.0.1:端口/api/version

如果页面显示：
未返回版本号-可能是旧版后端

说明你当前启动的不是新版 web服务控制台.exe，或者旧 Web 服务进程没有关闭。
