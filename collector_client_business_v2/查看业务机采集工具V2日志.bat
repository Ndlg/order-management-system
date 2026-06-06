@echo off
setlocal
set "APPDIR=%~dp0"
if not exist "%APPDIR%logs" mkdir "%APPDIR%logs"
start "" "%APPDIR%logs"
