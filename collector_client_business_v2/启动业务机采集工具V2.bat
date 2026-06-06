@echo off
setlocal
set "APPDIR=%~dp0"
set "EXE=%APPDIR%business_waybill_collector_v2.exe"
if not exist "%EXE%" (
  echo Missing business_waybill_collector_v2.exe
  pause
  exit /b 1
)
start "business waybill collector v2" "%EXE%"
