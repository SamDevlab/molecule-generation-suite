param(
    [string]$ExpectedHead = "",
    [int]$TimeoutSeconds = 120
)

$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
Set-Location $Repo

$branch = (@(git branch --show-current) -join "`n").Trim()
$head = (@(git rev-parse HEAD) -join "`n").Trim()
if ([string]::IsNullOrWhiteSpace($ExpectedHead)) {
    $ExpectedHead = $head
}

Write-Host "=== Research OS v5 Attempt 7 ==="
Write-Host "Branch: $branch"
Write-Host "HEAD: $head"
Write-Host "Expected HEAD: $ExpectedHead"
Write-Host "Codex: $(codex --version)"

if ($branch -ne "research-os-v1.3") {
    Write-Error "WRONG_BRANCH: expected research-os-v1.3"
    exit 2
}
if ($head -ne $ExpectedHead) {
    Write-Error "WRONG_HEAD: expected $ExpectedHead"
    exit 2
}
$dirty = @(git status --porcelain)
if ($dirty.Count -gt 0) {
    Write-Error "DIRTY_WORKTREE: resolve changes before Live execution"
    exit 2
}

& "$PSScriptRoot\run_v50_consistency_schema_smoke.ps1" -ExpectedHead $ExpectedHead -TimeoutSeconds $TimeoutSeconds
$smokeCode = $LASTEXITCODE
if ($smokeCode -ne 0) {
    if ($smokeCode -eq 2) {
        Write-Host "RUN_FROM_GENUINE_TOP_LEVEL_POWERSHELL"
    }
    Write-Host "V5_ATTEMPT_7_STOPPED_BEFORE_FULL_LIVE=$smokeCode"
    exit $smokeCode
}

Write-Host "Consistency schema smoke PASS; starting fresh 39-call Attempt 7."
& .\.venv\Scripts\python.exe -u `
    tools\benchmark\run_v50_live_top_level.py `
    --run-all `
    --expected-head $ExpectedHead `
    --timeout-seconds $TimeoutSeconds

$Code = $LASTEXITCODE
Write-Host "V5_ATTEMPT_7_EXIT_CODE=$Code"
exit $Code
