@echo off
setlocal
cd /d "%~dp0"
set "APPDIR=%~dp0"
set "EXE=%APPDIR%business_waybill_service.exe"
if not exist "%EXE%" (
    echo Missing service file: %EXE%
    pause
    exit /b 1
)
if not exist "%APPDIR%logs" mkdir "%APPDIR%logs"
start "Order Waybill Service" /min "%EXE%"
echo Order waybill service started.
echo Config file: %APPDIR%business_waybill_service.json
echo Log file: %APPDIR%logs\business_waybill_service.log
pause
