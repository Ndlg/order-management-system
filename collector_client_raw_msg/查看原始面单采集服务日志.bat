@echo off
setlocal
set "LOG=%~dp0logs\business_waybill_raw_msg_service.log"
if not exist "%LOG%" (
  echo Log file not found: %LOG%
  pause
  exit /b 1
)
notepad "%LOG%"
