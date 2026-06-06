@echo off
setlocal
set "APPDIR=%~dp0"
set "EXE=%APPDIR%business_waybill_raw_msg_service.exe"
if not exist "%EXE%" (
  echo Missing business_waybill_raw_msg_service.exe
  pause
  exit /b 1
)
start "raw waybill service" /min "%EXE%"
echo Raw waybill service started.
echo Config file: %APPDIR%business_waybill_raw_msg_service.json
echo Log file: %APPDIR%logs\business_waybill_raw_msg_service.log
pause
