param(
    [string]$PostgresSource = 'C:\Program Files\PostgreSQL\18',
    [int]$Port = 55432
)
$ErrorActionPreference = 'Stop'
$project = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$local = Join-Path $project '.local'
$runtime = Join-Path $local 'postgres'
$data = Join-Path $local 'pgdata'
$source = Join-Path $local 'pgvector-source'
$passwordFile = Join-Path $local 'postgres-password.txt'
$passFile = Join-Path $local 'pgpass.conf'
New-Item -ItemType Directory -Path $local -Force | Out-Null

if (-not (Test-Path -LiteralPath (Join-Path $PostgresSource 'bin\postgres.exe'))) {
    throw 'Pass -PostgresSource with a PostgreSQL 18 installation including development headers.'
}
New-Item -ItemType Directory -Path $runtime -Force | Out-Null
foreach ($part in @('bin', 'lib', 'share', 'include')) {
    $destination = Join-Path $runtime $part
    if (-not (Test-Path -LiteralPath $destination)) {
        Copy-Item -LiteralPath (Join-Path $PostgresSource $part) -Destination $destination -Recurse
    }
}

if (-not (Test-Path -LiteralPath (Join-Path $runtime 'share\extension\vector.control'))) {
    if (-not (Test-Path -LiteralPath (Join-Path $source '.git'))) {
        & git clone --depth 1 --branch v0.8.7 https://github.com/pgvector/pgvector.git $source
        if ($LASTEXITCODE -ne 0) { throw 'Could not download pgvector source.' }
    }
    $version = & git -C $source describe --tags --exact-match 2>$null
    if ($version -ne 'v0.8.7') {
        & git -C $source fetch --depth 1 origin tag v0.8.7
        if ($LASTEXITCODE -ne 0) { throw 'Could not fetch the pinned pgvector version.' }
        & git -C $source checkout --detach v0.8.7
        if ($LASTEXITCODE -ne 0) { throw 'Could not select the pinned pgvector version.' }
    }
    $vswhere = 'C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe'
    if (-not (Test-Path -LiteralPath $vswhere)) { throw 'Visual Studio C++ build tools are required for the Windows pgvector build.' }
    $vs = @(& $vswhere -all -products '*' -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath) | Select-Object -First 1
    if (-not $vs) { throw 'No C++ build tools installation was found.' }
    $vcvars = Join-Path $vs 'VC\Auxiliary\Build\vcvars64.bat'
    if (-not (Test-Path -LiteralPath $vcvars)) { throw 'The C++ compiler environment was not found.' }
    $batch = Join-Path $local 'build-vector.cmd'
    $batchText = @"
@echo off
call "$vcvars"
if errorlevel 1 exit /b 1
set "PGROOT=$runtime"
cd /d "$source"
nmake /F Makefile.win
if errorlevel 1 exit /b 1
nmake /F Makefile.win install
if errorlevel 1 exit /b 1
"@
    [IO.File]::WriteAllText($batch, $batchText, [Text.Encoding]::ASCII)
    & cmd.exe /d /c $batch
    if ($LASTEXITCODE -ne 0) { throw 'pgvector build failed.' }
}

if (-not (Test-Path -LiteralPath (Join-Path $data 'PG_VERSION'))) {
    if (-not (Test-Path -LiteralPath $passwordFile)) {
        $bytes = New-Object byte[] 32
        $generator = [Security.Cryptography.RandomNumberGenerator]::Create()
        $generator.GetBytes($bytes)
        $generator.Dispose()
        [IO.File]::WriteAllText($passwordFile, [Convert]::ToBase64String($bytes), [Text.UTF8Encoding]::new($false))
    }
    & (Join-Path $runtime 'bin\initdb.exe') -D $data -U fursah -A scram-sha-256 --pwfile=$passwordFile --encoding=UTF8 --locale=C
    if ($LASTEXITCODE -ne 0) { throw 'Could not initialize the project database cluster.' }
}
if (-not (Test-Path -LiteralPath $passwordFile)) { throw 'The existing project cluster needs its original local password file.' }
$password = [IO.File]::ReadAllText($passwordFile).Trim()
[IO.File]::WriteAllText($passFile, "127.0.0.1:${Port}:*:fursah:$password`n", [Text.UTF8Encoding]::new($false))
$env:PGPASSFILE = $passFile

& (Join-Path $runtime 'bin\pg_ctl.exe') -D $data status *> $null
if ($LASTEXITCODE -ne 0) {
    if (Get-NetTCPConnection -State Listen -LocalPort $Port -ErrorAction SilentlyContinue) { throw "Port $Port is already occupied. Choose another project port." }
    & (Join-Path $runtime 'bin\pg_ctl.exe') -D $data -l (Join-Path $local 'postgres.log') -o "-h 127.0.0.1 -p $Port" -w start
    if ($LASTEXITCODE -ne 0) { throw 'Could not start project PostgreSQL; inspect .local/postgres.log.' }
}
$psql = Join-Path $runtime 'bin\psql.exe'
$databaseExists = & $psql -h 127.0.0.1 -p $Port -U fursah -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='fursah_retrieval'"
if ($LASTEXITCODE -ne 0) { throw 'Project database connection failed.' }
if (-not ($databaseExists -match '^\s*1\s*$')) {
    & (Join-Path $runtime 'bin\createdb.exe') -h 127.0.0.1 -p $Port -U fursah fursah_retrieval
    if ($LASTEXITCODE -ne 0) { throw 'Could not create project database.' }
}
& $psql -h 127.0.0.1 -p $Port -U fursah -d fursah_retrieval -v ON_ERROR_STOP=1 -c 'CREATE EXTENSION IF NOT EXISTS vector;'
if ($LASTEXITCODE -ne 0) { throw 'Could not enable pgvector.' }
$config = @{ host='127.0.0.1'; port=$Port; user='fursah'; dbname='fursah_retrieval'; passfile=$passFile }
[IO.File]::WriteAllText((Join-Path $local 'database.json'), ($config | ConvertTo-Json), [Text.UTF8Encoding]::new($false))
Write-Output "Project database ready on 127.0.0.1:$Port."
