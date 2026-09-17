from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
ATTEMPT7 = REPO_ROOT / "tools" / "benchmark" / "run_v50_attempt7.ps1"
SMOKE = REPO_ROOT / "tools" / "benchmark" / "run_v50_consistency_schema_smoke.ps1"


def _preflight_result(branch: str, head: str, expected_head: str, dirty_lines: list[str]) -> tuple[int, str]:
    """Model only the bounded wrapper gates; never invokes PowerShell or Live."""
    if branch != "research-os-v1.3":
        return 2, "WRONG_BRANCH"
    if head != expected_head:
        return 2, "WRONG_HEAD"
    if len(dirty_lines) > 0:
        return 2, "DIRTY_WORKTREE"
    return 0, "CONTINUE_TO_SMOKE"


def test_attempt7_clean_native_status_is_counted_without_trim():
    source = ATTEMPT7.read_text(encoding="utf-8")
    assert "$dirty = @(git status --porcelain)" in source
    assert "$dirty.Count -gt 0" in source
    assert "git status --porcelain).Trim()" not in source
    assert _preflight_result("research-os-v1.3", "HEAD", "HEAD", []) == (0, "CONTINUE_TO_SMOKE")


def test_attempt7_dirty_native_status_stops_before_smoke():
    source = ATTEMPT7.read_text(encoding="utf-8")
    dirty_gate = source.index("$dirty = @(git status --porcelain)")
    smoke_call = source.index("run_v50_consistency_schema_smoke.ps1")
    assert dirty_gate < smoke_call
    assert _preflight_result("research-os-v1.3", "HEAD", "HEAD", [" M README.md"]) == (2, "DIRTY_WORKTREE")


def test_attempt7_wrong_branch_and_head_fail_before_smoke():
    source = ATTEMPT7.read_text(encoding="utf-8")
    smoke_call = source.index("run_v50_consistency_schema_smoke.ps1")
    assert source.index('WRONG_BRANCH: expected research-os-v1.3') < smoke_call
    assert source.index('WRONG_HEAD: expected $ExpectedHead') < smoke_call
    assert _preflight_result("main", "HEAD", "HEAD", []) == (2, "WRONG_BRANCH")
    assert _preflight_result("research-os-v1.3", "OTHER", "HEAD", []) == (2, "WRONG_HEAD")


def test_attempt7_starts_full_live_only_after_smoke_gate():
    source = ATTEMPT7.read_text(encoding="utf-8")
    smoke_call = source.index("run_v50_consistency_schema_smoke.ps1")
    smoke_result_gate = source.index("if ($smokeCode -ne 0)")
    full_live_call = source.index("run_v50_live_top_level.py")
    assert smoke_call < smoke_result_gate < full_live_call


def test_smoke_wrapper_has_null_safe_head_fallback():
    source = SMOKE.read_text(encoding="utf-8")
    assert '(@(git rev-parse HEAD) -join "`n").Trim()' in source
    assert "git rev-parse HEAD).Trim()" not in source
