@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo [清理] build / dist / spec / pycache
rmdir /s /q build 2>nul
rmdir /s /q dist 2>nul
del /q *.spec 2>nul
for /d /r %%d in (__pycache__) do @if exist "%%d" rmdir /s /q "%%d"
echo [完成] 已清理。
pause
