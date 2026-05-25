@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
cd /d "%~dp0"

set "PYTHON_EXE=python"

"%PYTHON_EXE%" --version >nul 2>nul
if errorlevel 1 (
    echo [错误] 未找到 python，请先安装 Python，并勾选 Add Python to PATH。
    pause
    exit /b 1
)

if not exist "order_backend_admin.py" (
    echo [错误] 当前目录不正确，缺少 order_backend_admin.py。
    echo 当前目录：%cd%
    pause
    exit /b 1
)

echo.
echo [准备] 安装/检查编译依赖...
"%PYTHON_EXE%" -m pip install --upgrade pip
if errorlevel 1 (
    echo [错误] pip 升级失败。
    pause
    exit /b 1
)

"%PYTHON_EXE%" -m pip install pandas openpyxl pillow cryptography fastapi uvicorn python-multipart pyinstaller
if errorlevel 1 (
    echo [错误] 依赖安装失败。
    pause
    exit /b 1
)

echo.
echo [编译] 订单整理管理系统.exe
"%PYTHON_EXE%" -m PyInstaller -F -w -n "订单整理管理系统" --icon "icon_backend.ico" --add-data "icon_backend.ico;." --add-data "icon_backend.png;." --hidden-import order_secure_common --collect-all PIL --collect-all cryptography order_backend_admin.py
if errorlevel 1 (
    echo [错误] 订单整理管理系统 编译失败。
    pause
    exit /b 1
)

echo.
echo [完成] 输出文件：dist\订单整理管理系统.exe
pause
