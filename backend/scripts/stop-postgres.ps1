$ErrorActionPreference = 'Stop'
$project = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$local = Join-Path $project '.local'
& (Join-Path $local 'postgres\bin\pg_ctl.exe') -D (Join-Path $local 'pgdata') -m fast -w stop
if ($LASTEXITCODE -ne 0) { throw 'Could not stop the project database.' }
