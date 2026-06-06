$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $Root
python ".\build_qt_windows.py"
if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}

