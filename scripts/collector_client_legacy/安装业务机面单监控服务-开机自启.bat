@echo off
setlocal
cd /d "%~dp0"
set "EXE=%~dp0business_waybill_service.exe"
if not exist "%EXE%" (
    echo Missing service file: %EXE%
    pause
    exit /b 1
)
schtasks /Create /TN "Order Waybill Monitor Service" /SC ONLOGON /TR "\"%EXE%\"" /F
echo Installed startup task: Order Waybill Monitor Service
pause
