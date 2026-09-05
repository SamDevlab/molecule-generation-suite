"""Top-level ownership and repository preflight contracts for v5 Live runs.

This module never starts Codex.  It only answers whether the current process
may own the fixed Live launcher and whether the stored Research OS state is
ready for that launcher.  The actual 39-call Live sequence lives in the
operational script under ``tools/benchmark`` and is intentionally not run by
the current Codex development session.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from enum import Enum
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import sys
from typing import Any, Mapping
import uuid


class TopLevelOwnerResult(str, Enum):
    TOP_LEVEL_CONFIRMED = "TOP_LEVEL_CONFIRMED"
    TOP_LEVEL_OWNER_REQUIRED = "TOP_LEVEL_OWNER_REQUIRED"
    ENVIRONMENT_AMBIGUOUS = "ENVIRONMENT_AMBIGUOUS"
    PROCESS_INSPECTION_FAILED = "PROCESS_INSPECTION_FAILED"


class TopLevelPreflightStatus(str, Enum):
    READY = "READY"
    WRONG_BRANCH = "WRONG_BRANCH"
    DIRTY_WORKTREE = "DIRTY_WORKTREE"
    LEDGER_INVALID = "LEDGER_INVALID"
    PACKAGE_INVALID = "PACKAGE_INVALID"
    CODEX_CLI_MISSING = "CODEX_CLI_MISSING"
    NESTED_CODEX_DETECTED = "NESTED_CODEX_DETECTED"
    ARTIFACT_MISSING = "ARTIFACT_MISSING"
    SCHEMA_INVALID = "SCHEMA_INVALID"
    PROVIDER_INVALID = "PROVIDER_INVALID"
    GIT_INSPECTION_FAILED = "GIT_INSPECTION_FAILED"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _environment_digest(environment: Mapping[str, str]) -> str:
    safe: dict[str, str] = {}
    for key, value in sorted(environment.items()):
        safe[key] = "[REDACTED]" if re.search(r"token|secret|password|key|credential", key, re.I) else str(value)
    return hashlib.sha256(json.dumps(safe, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class TopLevelLiveOwnerDiagnostic:
    invocation_id: str
    pid: int
    parent_pid: int
    process_name: str
    parent_process_name: str
    ancestry_summary: tuple[str, ...]
    codex_session_detected: bool
    detection_signals: tuple[str, ...]
    top_level_eligible: bool
    executable: str
    cwd: str
    environment_digest: str
    started_at: str
    result: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class TopLevelPreflight:
    status: str
    root: str
    branch: str | None
    head: str | None
    expected_branch: str
    expected_head: str | None
    owner: TopLevelLiveOwnerDiagnostic
    checks: dict[str, Any]
    started_at: str
    completed_at: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class V5LiveAcceptanceDigest:
    repository_commit: str
    reviewer_artifact_hash: str
    final_exam_artifact_hash: str
    followup_artifact_hash: str
    stress_artifact_hash: str
    consistency_artifact_hash: str
    process_cleanup_hash: str
    scientific_audit_hash: str
    security_audit_hash: str
    live_call_count: int
    pass_: bool
    digest: str = ""

    def __post_init__(self) -> None:
        if not self.digest:
            body = {key: value for key, value in asdict(self).items() if key != "digest"}
            object.__setattr__(self, "digest", hashlib.sha256(json.dumps(body, sort_keys=True).encode("utf-8")).hexdigest())

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["pass"] = value.pop("pass_")
        return value


def _windows_process_table() -> dict[int, tuple[int, str]]:
    import ctypes
    from ctypes import wintypes

    class ProcessEntry(ctypes.Structure):
        _fields_ = [
            ("dwSize", wintypes.DWORD),
            ("cntUsage", wintypes.DWORD),
            ("th32ProcessID", wintypes.DWORD),
            ("th32DefaultHeapID", ctypes.c_size_t),
            ("th32ModuleID", wintypes.DWORD),
            ("cntThreads", wintypes.DWORD),
            ("th32ParentProcessID", wintypes.DWORD),
            ("pcPriClassBase", wintypes.LONG),
            ("dwFlags", wintypes.DWORD),
            ("szExeFile", wintypes.WCHAR * 260),
        ]

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    snapshot = kernel32.CreateToolhelp32Snapshot(0x00000002, 0)
    invalid = ctypes.c_void_p(-1).value
    if snapshot == invalid:
        raise OSError(ctypes.get_last_error(), "CreateToolhelp32Snapshot failed")
    try:
        first = kernel32.Process32FirstW
        next_process = kernel32.Process32NextW
        first.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        first.restype = wintypes.BOOL
        next_process.argtypes = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)]
        next_process.restype = wintypes.BOOL
        entry = ProcessEntry()
        entry.dwSize = ctypes.sizeof(ProcessEntry)
        table: dict[int, tuple[int, str]] = {}
        if not first(snapshot, ctypes.byref(entry)):
            raise OSError(ctypes.get_last_error(), "Process32FirstW failed")
        while True:
            table[int(entry.th32ProcessID)] = (int(entry.th32ParentProcessID), str(entry.szExeFile))
            if not next_process(snapshot, ctypes.byref(entry)):
                break
        return table
    finally:
        kernel32.CloseHandle(snapshot)


def _posix_process_table() -> dict[int, tuple[int, str]]:
    table: dict[int, tuple[int, str]] = {}
    proc_root = Path("/proc")
    for path in proc_root.iterdir():
        if not path.name.isdigit():
            continue
        try:
            stat = (path / "stat").read_text(encoding="utf-8")
            end_comm = stat.rfind(")")
            fields = stat[end_comm + 2 :].split()
            parent = int(fields[1])
            name = (path / "comm").read_text(encoding="utf-8").strip()
            table[int(path.name)] = (parent, name)
        except (OSError, ValueError, IndexError):
            continue
    if not table:
        raise OSError("/proc process table unavailable")
    return table


def _process_table() -> dict[int, tuple[int, str]]:
    if platform.system().lower() == "windows":
        return _windows_process_table()
    return _posix_process_table()


def inspect_top_level_owner(*, environment: Mapping[str, str] | None = None, process_table: Mapping[int, tuple[int, str]] | None = None, pid: int | None = None, parent_pid: int | None = None) -> TopLevelLiveOwnerDiagnostic:
    env = dict(environment if environment is not None else os.environ)
    current_pid = int(pid if pid is not None else os.getpid())
    resolved_parent_pid = int(parent_pid if parent_pid is not None else os.getppid())
    signals: list[str] = []
    session_markers = ("CODEX_THREAD_ID", "CODEX_SESSION_ID", "CODEX_INTERNAL_ORIGINATOR_OVERRIDE")
    for marker in session_markers:
        if env.get(marker):
            signals.append(f"{marker}_PRESENT")
    table_error: str | None = None
    try:
        table = dict(process_table if process_table is not None else _process_table())
    except (OSError, RuntimeError) as exc:
        table = {}
        table_error = type(exc).__name__
    current_info = table.get(current_pid)
    parent_info = table.get(resolved_parent_pid)
    process_name = current_info[1] if current_info else Path(sys.executable).name
    parent_name = parent_info[1] if parent_info else "UNKNOWN"
    ancestry: list[str] = []
    cursor = current_pid
    visited: set[int] = set()
    while cursor and cursor not in visited:
        visited.add(cursor)
        info = table.get(cursor)
        if info is None:
            break
        parent, name = info
        ancestry.append(f"{cursor}:{name}<-{parent}")
        if "codex" in name.lower() and cursor != current_pid:
            signals.append("ANCESTRY_PROCESS_NAME_CONTAINS_CODEX")
        if "codex" in name.lower() and cursor == resolved_parent_pid:
            signals.append("PARENT_PROCESS_NAME_CONTAINS_CODEX")
        cursor = parent
    if "codex" in process_name.lower():
        signals.append("CURRENT_PROCESS_NAME_CONTAINS_CODEX")
    codex_detected = bool(signals)
    if codex_detected:
        result = TopLevelOwnerResult.TOP_LEVEL_OWNER_REQUIRED.value
        eligible = False
    elif table_error:
        result = TopLevelOwnerResult.PROCESS_INSPECTION_FAILED.value
        eligible = False
        signals.append(f"PROCESS_INSPECTION_ERROR:{table_error}")
    elif not parent_info:
        result = TopLevelOwnerResult.ENVIRONMENT_AMBIGUOUS.value
        eligible = False
        signals.append("PARENT_PROCESS_NOT_RESOLVED")
    else:
        result = TopLevelOwnerResult.TOP_LEVEL_CONFIRMED.value
        eligible = True
    return TopLevelLiveOwnerDiagnostic(
        invocation_id=f"TOPLEVEL-{uuid.uuid4().hex[:16].upper()}",
        pid=current_pid,
        parent_pid=resolved_parent_pid,
        process_name=process_name,
        parent_process_name=parent_name,
        ancestry_summary=tuple(ancestry),
        codex_session_detected=codex_detected,
        detection_signals=tuple(dict.fromkeys(signals)),
        top_level_eligible=eligible,
        executable=sys.executable,
        cwd=os.getcwd(),
        environment_digest=_environment_digest(env),
        started_at=_utc_now(),
        result=result,
    )


def _fixed_git(root: Path, *args: str) -> tuple[bool, str]:
    git = shutil.which("git")
    if not git:
        return False, "git executable unavailable"
    try:
        result = subprocess.run([git, *args], cwd=root, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=10, check=False, shell=False)
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"{type(exc).__name__}: {exc}"
    if result.returncode != 0:
        return False, result.stderr.strip()[:240]
    return True, result.stdout.strip()


def preflight_repository(root: str | os.PathLike[str], *, expected_branch: str = "research-os-v1.3", expected_head: str | None = None, environment: Mapping[str, str] | None = None, process_table: Mapping[int, tuple[int, str]] | None = None) -> TopLevelPreflight:
    started = _utc_now()
    repo_root = Path(root).resolve()
    owner = inspect_top_level_owner(environment=environment, process_table=process_table)
    branch_ok, branch_value = _fixed_git(repo_root, "branch", "--show-current")
    head_ok, head_value = _fixed_git(repo_root, "rev-parse", "HEAD")
    clean_ok, clean_value = _fixed_git(repo_root, "status", "--porcelain=v1")
    checks: dict[str, Any] = {
        "branch": {"ok": branch_ok and branch_value == expected_branch, "value": branch_value},
        "head": {"ok": head_ok and (expected_head is None or head_value == expected_head), "value": head_value, "expected": expected_head},
        "worktree": {"ok": clean_ok and not clean_value, "value": clean_value},
        "owner": owner.to_dict(),
        "required_artifacts": [],
        "ledger": {"ok": False, "status": "NOT_CHECKED"},
        "package": {"ok": False, "version": None},
        "schema": {"ok": False},
        "provider": {"ok": False},
        "codex_cli": {"ok": bool(shutil.which("codex"))},
    }
    required = (
        repo_root / ".research-os-live-5.0" / "master-real-research-validation.json",
        repo_root / ".research-os-live-5.0" / "final-scientific-exam.json",
        repo_root / ".research-os-live-5.0" / "reviewer-panel.json",
        repo_root / ".research-os-live-5.0" / "reproduction-matrix.json",
        repo_root / ".research-os-live-5.0" / "ledger" / "research_ledger.sqlite",
    )
    checks["required_artifacts"] = [{"path": str(path), "exists": path.is_file()} for path in required]
    try:
        from research_os.ledger import verify_ledger

        ledger_result = verify_ledger(required[-1])
        checks["ledger"] = {"ok": ledger_result.status == "PASS", "status": ledger_result.status}
    except Exception as exc:  # pragma: no cover - defensive preflight boundary
        checks["ledger"] = {"ok": False, "status": f"ERROR:{type(exc).__name__}"}
    try:
        from importlib.metadata import version

        import research_os
        from research_os.oracle import CodexCliTransport

        package_version = version("research-os-core")
        checks["package"] = {"ok": package_version == "4.5.0" and research_os is not None, "version": package_version}
        schema = json.loads((repo_root / "src" / "research_os" / "oracle" / "live_output.schema.json").read_text(encoding="utf-8"))
        checks["schema"] = {"ok": schema.get("type") == "object" and schema.get("required") == ["result"] and schema.get("additionalProperties") is False}
        transport = CodexCliTransport(environment={})
        checks["provider"] = {"ok": transport.schema_path.is_file() and transport._APPROVED_EXECUTABLE_NAMES == {"codex", "codex.exe"}, "type": type(transport).__name__}
    except Exception as exc:  # pragma: no cover - defensive preflight boundary
        checks["package"]["error"] = f"{type(exc).__name__}: {exc}"
    if not branch_ok or not head_ok or not clean_ok:
        status = TopLevelPreflightStatus.GIT_INSPECTION_FAILED.value
    elif not checks["branch"]["ok"]:
        status = TopLevelPreflightStatus.WRONG_BRANCH.value
    elif not checks["head"]["ok"]:
        status = TopLevelPreflightStatus.WRONG_BRANCH.value
    elif not checks["worktree"]["ok"]:
        status = TopLevelPreflightStatus.DIRTY_WORKTREE.value
    elif owner.result != TopLevelOwnerResult.TOP_LEVEL_CONFIRMED.value:
        status = TopLevelPreflightStatus.NESTED_CODEX_DETECTED.value if owner.codex_session_detected else owner.result
    elif not all(item["exists"] for item in checks["required_artifacts"]):
        status = TopLevelPreflightStatus.ARTIFACT_MISSING.value
    elif not checks["ledger"]["ok"]:
        status = TopLevelPreflightStatus.LEDGER_INVALID.value
    elif not checks["package"]["ok"]:
        status = TopLevelPreflightStatus.PACKAGE_INVALID.value
    elif not checks["schema"]["ok"]:
        status = TopLevelPreflightStatus.SCHEMA_INVALID.value
    elif not checks["provider"]["ok"]:
        status = TopLevelPreflightStatus.PROVIDER_INVALID.value
    elif not checks["codex_cli"]["ok"]:
        status = TopLevelPreflightStatus.CODEX_CLI_MISSING.value
    else:
        status = TopLevelPreflightStatus.READY.value
    return TopLevelPreflight(status, str(repo_root), branch_value if branch_ok else None, head_value if head_ok else None, expected_branch, expected_head, owner, checks, started, _utc_now())
