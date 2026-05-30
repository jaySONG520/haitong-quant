param(
  [Parameter(Mandatory = $true)]
  [string]$WebhookUrl,
  [string]$Title = "Haitong Quant Notify Test",
  [string]$Body = "WeCom notification is connected. No trading action is involved."
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
& $VenvPython -m haitong_quant.cli notify-test --config configs/default.json --notifier wechat --title $Title --body $Body
