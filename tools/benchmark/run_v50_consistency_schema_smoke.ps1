param(
    [string]$ExpectedHead = "",
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Repo

if ([string]::IsNullOrWhiteSpace($ExpectedHead)) {
    $ExpectedHead = (git rev-parse HEAD).Trim()
}

Write-Host "=== Research OS v5 Consistency Schema Smoke ==="
Write-Host "Branch: $(git branch --show-current)"
Write-Host "HEAD: $(git rev-parse HEAD)"
Write-Host "Expected HEAD: $ExpectedHead"
Write-Host "Codex: $(codex --version)"

& .\.venv\Scripts\python.exe -u `
    tools\benchmark\run_v50_consistency_schema_smoke.py `
    --expected-head $ExpectedHead `
    --timeout-seconds $TimeoutSeconds

$Code = $LASTEXITCODE
Write-Host "V5_CONSISTENCY_SCHEMA_SMOKE_EXIT_CODE=$Code"
exit $Code
