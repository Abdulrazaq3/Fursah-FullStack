$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
& npm --prefix (Join-Path $project 'frontend') run dev
if ($LASTEXITCODE -ne 0) { throw 'Frontend stopped with an error.' }
