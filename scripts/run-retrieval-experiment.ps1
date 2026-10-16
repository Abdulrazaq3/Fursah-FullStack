$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) {
    & (Join-Path $PSScriptRoot 'setup-python.ps1')
}
& (Join-Path $PSScriptRoot 'setup-postgres.ps1')
Push-Location $project
try {
    & $python (Join-Path $PSScriptRoot 'download-model.py') --check-only
    if ($LASTEXITCODE -ne 0) {
        & $python (Join-Path $PSScriptRoot 'download-model.py')
        if ($LASTEXITCODE -ne 0) { throw 'Model download did not complete. No real retrieval evaluation was run.' }
    }
    & $python (Join-Path $project 'experiments\local_retrieval.py')
    if ($LASTEXITCODE -ne 0) { throw 'Retrieval experiment failed; do not treat previous results as this run.' }
    & $python (Join-Path $project 'experiments\review_results.py')
    if ($LASTEXITCODE -ne 0) { throw 'Results review generation failed.' }
    Write-Output 'Finished. Read results/retrieval-review.md for measured results and limitations.'
} finally {
    Pop-Location
}
