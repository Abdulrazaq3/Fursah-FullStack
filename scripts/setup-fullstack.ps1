$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3.11 -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $python -m pip install -r (Join-Path $project 'backend\requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'Backend dependencies installation failed.' }
& npm --prefix (Join-Path $project 'frontend') ci
if ($LASTEXITCODE -ne 0) { throw 'Frontend dependencies installation failed.' }
Write-Output 'Frontend and API shell are prepared. See README.md for startup and current limitations.'
