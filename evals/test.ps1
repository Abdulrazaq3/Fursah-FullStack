$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
$previousPath = $env:PYTHONPATH
try {
    $env:PYTHONPATH = @($project,(Join-Path $project 'backend'),(Join-Path $project 'evals\archive\experiments'),(Join-Path $project 'backend\app\infrastructure\models')) -join [IO.Path]::PathSeparator
    Push-Location $project
    try {
        & $python -X utf8 -m unittest discover -s evals/tests/backend -q
        if ($LASTEXITCODE -ne 0) { throw 'Backend regression checks failed.' }
        & $python -X utf8 -m unittest discover -s evals/tests/experiments -p 'test_*.py' -q
        if ($LASTEXITCODE -ne 0) { throw 'Experiment regression checks failed.' }
    } finally { Pop-Location }
} finally { $env:PYTHONPATH = $previousPath }
