param(
    [ValidatePattern('^[A-Za-z0-9_-]{1,80}$')][string]$Label = 'catalog-check',
    [ValidatePattern('^[A-Za-z0-9,_-]*$')][string]$Only = '',
    [switch]$Demo,
    [switch]$Open,
    [switch]$OfflineTraces
)
$ErrorActionPreference = 'Stop'
$project = Split-Path $PSScriptRoot -Parent
$python = Join-Path $project '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $python)) { throw 'Run backend/setup.ps1 -Models -Evals first.' }
if ($Demo -and $Only) { throw 'Choose -Demo or -Only.' }
if ($Demo) { $Only = 'CAT-DEV-02,CAT-DEV-05,CAT-DEV-07' }
if (-not $OfflineTraces) { & (Join-Path $PSScriptRoot 'phoenix.ps1') }
$previousCatalog = $env:FURSAH_CATALOG_MODE
$previousUnderstanding = $env:FURSAH_UNDERSTANDING_MODE
$previousEndpoint = $env:FURSAH_PHOENIX_ENDPOINT
try {
    $env:FURSAH_CATALOG_MODE = 'prepared'
    $env:FURSAH_UNDERSTANDING_MODE = 'active'
    $env:FURSAH_PHOENIX_ENDPOINT = 'http://127.0.0.1:6006/v1/traces'
    Push-Location $project
    try {
        $export = if ($OfflineTraces) { 'memory' } else { 'phoenix' }
        $arguments = @('-u','-X','utf8','-m','evals.run','--trace-export',$export,'--label',$Label)
        if ($Only) { $arguments += @('--only',$Only) }
        & $python @arguments
        $resultCode = $LASTEXITCODE
        if ($resultCode -eq 2) { Write-Warning 'Evaluation completed with failed cases. Inspect the saved results and traces.' }
        elseif ($resultCode -ne 0) { throw 'Evaluation could not complete. Inspect the error above.' }
        if ($Open -and -not $OfflineTraces) { Start-Process 'http://127.0.0.1:6006' }
    } finally { Pop-Location }
} finally {
    $env:FURSAH_CATALOG_MODE = $previousCatalog
    $env:FURSAH_UNDERSTANDING_MODE = $previousUnderstanding
    $env:FURSAH_PHOENIX_ENDPOINT = $previousEndpoint
}
exit $resultCode
