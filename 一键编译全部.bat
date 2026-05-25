@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ====================================
echo Order Sorter - Build All
echo ====================================
echo Current dir: %cd%
echo.

if not exist "order_backend_admin.py" (
    echo ERROR: order_backend_admin.py not found.
    echo Please put this BAT file in the project folder.
    echo.
    pause
    exit /b 1
)

py -3 --version >nul 2>nul
if errorlevel 1 (
    python --version >nul 2>nul
    if errorlevel 1 (
        echo ERROR: Python not found.
        echo Please install Python and add it to PATH.
        echo.
        pause
        exit /b 1
    )
    set "PY=python"
) else (
    set "PY=py -3"
)

echo Using Python:
%PY% --version
echo.

echo Installing dependencies...
%PY% -m pip install pandas openpyxl pillow cryptography fastapi uvicorn python-multipart pyinstaller
if errorlevel 1 (
    echo.
    echo ERROR: dependency install failed.
    echo.
    pause
    exit /b 1
)

echo.
echo Cleaning old build files...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist
del /q *.spec 2>nul

echo.
echo [1/3] Building backend admin...
%PY% -m PyInstaller -F -w -n "订单整理管理系统" --icon="icon_backend.ico" --add-data "icon_backend.ico;." --add-data "icon_backend.png;." --hidden-import=order_secure_common --collect-all PIL --collect-all cryptography order_backend_admin.py
if errorlevel 1 (
    echo.
    echo ERROR: backend admin build failed.
    echo.
    pause
    exit /b 1
)

echo.
echo [2/3] Building frontend sorter...
%PY% -m PyInstaller -F -w -n "一键整理订单" --icon="icon_frontend.ico" --add-data "icon_frontend.ico;." --add-data "icon_frontend.png;." --hidden-import=order_secure_common --hidden-import=order_core --collect-all PIL --collect-all cryptography order_frontend.py
if errorlevel 1 (
    echo.
    echo ERROR: frontend sorter build failed.
    echo.
    pause
    exit /b 1
)

echo.
echo [3/3] Building web console...
%PY% -m PyInstaller -F -w -n "web服务控制台" --icon="icon_web.ico" --add-data "icon_web.ico;." --add-data "icon_web.png;." --add-data "templates;templates" --hidden-import=app --hidden-import=order_secure_common --hidden-import=order_core --collect-all fastapi --collect-all starlette --collect-all uvicorn --collect-all PIL --collect-all cryptography web_launcher.py
if errorlevel 1 (
    echo.
    echo ERROR: web console build failed.
    echo If permission denied, close old exe in dist and try again.
    echo.
    pause
    exit /b 1
)

echo.
echo ====================================
echo Build finished.
echo Output folder: %cd%\dist
echo ====================================
echo.
pause
