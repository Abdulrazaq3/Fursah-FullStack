param([int]$Port = 8000, [switch]$Reload)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run backend/setup.ps1 first.' }
Push-Location (Join-Path $project 'backend')
try {
    $arguments = @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', "$Port")
    if ($Reload) { $arguments += '--reload' }
    & $python @arguments
    if ($LASTEXITCODE -ne 0) { throw 'Backend stopped with an error.' }
} finally { Pop-Location }
