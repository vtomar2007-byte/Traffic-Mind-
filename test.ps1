$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (-not (Test-Path $python)) { throw 'Project environment is missing. Run .\setup.ps1 first.' }
& $python -m pytest -q
if ($LASTEXITCODE -ne 0) { throw 'TrafficMind tests failed.' }
