param([switch]$Models, [switch]$Evals, [switch]$Frontend)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3.11 -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
$requirements = @('-r', (Join-Path $PSScriptRoot 'requirements.txt'))
if ($Models) {
    & $python -m pip install 'torch==2.14.1+cpu' --index-url https://download.pytorch.org/whl/cpu
    if ($LASTEXITCODE -ne 0) { throw 'CPU PyTorch installation failed.' }
    $requirements += @('-r', (Join-Path $PSScriptRoot 'requirements-models.lock.txt'),
        '-r', (Join-Path $project 'data\requirements.txt'))
}
if ($Evals) { $requirements += @('-r', (Join-Path $project 'evals\requirements.txt')) }
& $python -m pip install @requirements
if ($LASTEXITCODE -ne 0) { throw 'Python dependency installation failed.' }
if ($Frontend) {
    & npm --prefix (Join-Path $project 'frontend') ci
    if ($LASTEXITCODE -ne 0) { throw 'Frontend dependency installation failed.' }
}
Write-Output 'Dependencies ready. See README.md for model downloads, database setup, startup and evaluation.'
