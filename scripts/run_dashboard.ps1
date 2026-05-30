param(
  [string]$Config = "configs/default.json",
  [string]$HostName = "127.0.0.1",
  [int]$Port = 8765
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  $VenvPython = Join-Path $ProjectRoot ".venv\bin\python.exe"
}
if (-not (Test-Path $VenvPython)) {
  $VenvPython = Join-Path $ProjectRoot ".venv\bin\python"
}
if (-not (Test-Path $VenvPython)) {
  throw ".venv was not found. Run first: powershell -ExecutionPolicy Bypass -File scripts/setup_env.ps1"
}

$env:PYTHONPATH = Join-Path $ProjectRoot "src"
& $VenvPython -m haitong_quant.cli dashboard --config $Config --serve --host $HostName --port $Port
