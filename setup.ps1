$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$launcher = $null
$pythonArgs = @()
if (Get-Command py -ErrorAction SilentlyContinue) {
  try { & py -3.12 -c "import sys; print(sys.version)" *> $null; if ($LASTEXITCODE -eq 0) { $launcher = 'py'; $pythonArgs = @('-3.12') } } catch {}
}
if (-not $launcher -and (Get-Command python -ErrorAction SilentlyContinue)) {
  try { & python -c "import sys; print(sys.version)" *> $null; if ($LASTEXITCODE -eq 0) { $launcher = 'python'; $pythonArgs = @() } } catch {}
}
if (-not $launcher) { throw 'Python 3.11 or 3.12 was not found. Install 64-bit Python from python.org, enable the launcher/PATH option, reopen PowerShell, then rerun .\setup.ps1.' }
$version = & $launcher @pythonArgs -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
if ($version -notin @('3.11','3.12')) { throw "TrafficMind supports Python 3.11 or 3.12; found $version." }
if (-not (Test-Path '.venv\Scripts\python.exe')) { & $launcher @pythonArgs -m venv .venv; if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' } }
& .\.venv\Scripts\python.exe -m pip --version *> $null
if ($LASTEXITCODE -ne 0) {
  $tempRoot = Join-Path $root '.trafficmind-tmp'
  New-Item -ItemType Directory -Path $tempRoot -Force | Out-Null
  $savedTemp = $env:TEMP; $savedTmp = $env:TMP
  $env:TEMP = $tempRoot; $env:TMP = $tempRoot
  & .\.venv\Scripts\python.exe -m ensurepip --upgrade
  $env:TEMP = $savedTemp; $env:TMP = $savedTmp
  if ($LASTEXITCODE -ne 0) { throw 'Could not bootstrap pip into the project virtual environment.' }
}
& .\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
if ($LASTEXITCODE -ne 0) { throw 'Dependency installation failed. Check the pip output and network connection.' }
Write-Host 'Setup complete. Start TrafficMind with .\run.ps1'
