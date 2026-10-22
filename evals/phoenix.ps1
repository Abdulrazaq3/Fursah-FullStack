param([switch]$Open)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
$address = 'http://127.0.0.1:6006'
function Test-Phoenix {
    try { return (Invoke-WebRequest "$address/healthz" -UseBasicParsing -TimeoutSec 2).StatusCode -eq 200 }
    catch { return $false }
}
if (-not (Test-Phoenix)) {
    if (-not (Test-Path -LiteralPath $python)) { throw 'Prepare the project Python environment first.' }
    & $python -c 'import phoenix.server.main' 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'Install evals/requirements.txt first.' }
    $state = Join-Path $project '.local\phoenix'
    New-Item -ItemType Directory -Force -Path $state | Out-Null
    $saved = @{}
    foreach ($key in @('PHOENIX_WORKING_DIR','PHOENIX_HOST','PHOENIX_PORT','PHOENIX_ENABLE_PROMETHEUS')) {
        $saved[$key] = [Environment]::GetEnvironmentVariable($key,'Process')
    }
    try {
        $env:PHOENIX_WORKING_DIR = $state
        $env:PHOENIX_HOST = '127.0.0.1'
        $env:PHOENIX_PORT = '6006'
        $env:PHOENIX_ENABLE_PROMETHEUS = 'false'
        $process = Start-Process -FilePath $python -ArgumentList '-m','phoenix.server.main','serve' -WorkingDirectory $project -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $state 'server.log') -RedirectStandardError (Join-Path $state 'server-error.log')
        $process.Id | Set-Content -LiteralPath (Join-Path $state 'server.pid')
    } finally {
        foreach ($key in $saved.Keys) { [Environment]::SetEnvironmentVariable($key,$saved[$key],'Process') }
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(90)
    do {
        if (Test-Phoenix) { break }
        if ($process.HasExited) { throw "Phoenix stopped. Read $state\server-error.log" }
        Start-Sleep -Milliseconds 500
    } while ([DateTime]::UtcNow -lt $deadline)
    if (-not (Test-Phoenix)) { throw "Phoenix is not ready. Read $state\server-error.log" }
}
Write-Host "Phoenix: $address | project: fursah-eval"
if ($Open) { Start-Process $address }
