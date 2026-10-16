$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & py -3.11 -m venv (Join-Path $project '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'Could not create the Python environment.' }
}
& $python -m pip install 'torch==2.14.1+cpu' --index-url https://download.pytorch.org/whl/cpu
if ($LASTEXITCODE -ne 0) { throw 'CPU PyTorch installation failed.' }
$requirements = Join-Path $project 'requirements-retrieval.lock.txt'
if (-not (Test-Path -LiteralPath $requirements)) { $requirements = Join-Path $project 'requirements-retrieval.txt' }
& $python -m pip install -r $requirements
if ($LASTEXITCODE -ne 0) { throw 'Retrieval dependencies installation failed.' }
