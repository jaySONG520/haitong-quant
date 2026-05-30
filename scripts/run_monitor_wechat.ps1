param(
  [Parameter(Mandatory = $true)]
  [string]$WebhookUrl,
  [string]$Config = "configs/default.json",
  [string]$TradePlan = "reports/trade_plan.json",
  [double]$IntervalSeconds = 60
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
$env:HAITONG_QUANT_WECHAT_WEBHOOK_URL = $WebhookUrl
& $VenvPython -m haitong_quant.cli monitor --config $Config --trade-plan $TradePlan --notifier wechat --interval-seconds $IntervalSeconds
