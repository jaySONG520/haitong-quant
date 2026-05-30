param(
  [string]$Python = "",
  [switch]$Recreate,
  [switch]$Research
)

$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

function Resolve-SetupPython {
  if ($Python) {
    return $Python
  }
  $Candidates = @(
    "C:\Python\python.exe",
    "C:\Program Files\python\python.exe",
    "python"
  )
  foreach ($Candidate in $Candidates) {
    if ($Candidate -eq "python") {
      return $Candidate
    }
    if (Test-Path $Candidate) {
      return $Candidate
    }
  }
}

function Invoke-Checked {
  param(
    [Parameter(Mandatory = $true)]
    [string]$Exe,
    [Parameter(Mandatory = $true)]
    [string[]]$Arguments
  )
  & $Exe @Arguments
  if ($LASTEXITCODE -ne 0) {
    throw "Command failed with exit code ${LASTEXITCODE}: $Exe $($Arguments -join ' ')"
  }
}

$SetupPython = Resolve-SetupPython
$VenvPath = Join-Path $ProjectRoot ".venv"
$VenvConfig = Join-Path $VenvPath "pyvenv.cfg"

if ((Test-Path $VenvConfig) -and -not $Recreate) {
  $VenvText = Get-Content -Path $VenvConfig -Raw
  if ($VenvText -match "msys64" -and $SetupPython -notmatch "msys64") {
    $Recreate = $true
  }
}

if ($Recreate -and (Test-Path $VenvPath)) {
  $ResolvedProject = (Resolve-Path $ProjectRoot).Path
  $ResolvedVenv = (Resolve-Path $VenvPath).Path
  if (-not $ResolvedVenv.StartsWith($ResolvedProject)) {
    throw "Refusing to remove venv outside project root: $ResolvedVenv"
  }
  Remove-Item -LiteralPath $ResolvedVenv -Recurse -Force
}

if (-not (Test-Path ".venv")) {
  Invoke-Checked $SetupPython @("-m", "venv", ".venv")
}

$VenvPython = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $VenvPython)) {
  $VenvPython = Join-Path $ProjectRoot ".venv\bin\python.exe"
}
if (-not (Test-Path $VenvPython)) {
  $VenvPython = Join-Path $ProjectRoot ".venv\bin\python"
}
if (-not (Test-Path $VenvPython)) {
  throw "Virtualenv Python was not found. Check whether .venv was created successfully."
}

Invoke-Checked $VenvPython @("-m", "pip", "install", "--upgrade", "pip")
Invoke-Checked $VenvPython @("-m", "pip", "install", "--no-cache-dir", "-e", ".[web,dev]")

if ($Research) {
  Invoke-Checked $VenvPython @("-m", "pip", "install", "--no-cache-dir", "-e", ".[research]")
}

Write-Host "Haitong quant local environment is ready:" $VenvPython
