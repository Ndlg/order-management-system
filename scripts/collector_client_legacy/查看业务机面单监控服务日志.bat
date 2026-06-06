@echo off
setlocal
cd /d "%~dp0"
set "LOG=%~dp0logs\business_waybill_service.log"
if not exist "%LOG%" (
    echo Log file does not exist yet: %LOG%
    pause
    exit /b 0
)
notepad "%LOG%"
