"""Persistent Research OS ledger public API.

Imports are resolved lazily so bundle creation can use the artifact store
without creating a circular dependency through the registry.
"""

from research_os.ledger.schema import (
    ClaimIndexRecord,
    EvidenceIndexRecord,
    FirstDivergence,
    LedgerConflictError,
    LedgerError,
    LedgerGate,
    LedgerIntegrityError,
    LedgerOperationStatus,
    LedgerRegistration,
    LedgerSchemaError,
    LedgerVerificationResult,
    LedgerVerificationStatus,
    LineageCycleError,
    LineageGraph,
    RebuildReport,
    ReproducibilityStatus,
    RunDependency,
    RunIndexRecord,
    WorkflowComparison,
    WorkflowExecution,
    WorkflowRerunResult,
    WorkflowStepIndex,
)

__all__ = [
    "ClaimIndexRecord", "EvidenceIndexRecord", "FirstDivergence", "LedgerConflictError", "LedgerError", "LedgerGate", "LedgerIntegrityError", "LedgerOperationStatus", "LedgerRegistration", "LedgerSchemaError", "LedgerVerificationResult", "LedgerVerificationStatus", "LineageCycleError", "LineageGraph", "RebuildReport", "ReproducibilityStatus", "RunDependency", "RunIndexRecord", "RunRegistry", "WorkflowComparison", "WorkflowExecution", "WorkflowRerunResult", "WorkflowStepIndex", "get_run", "list_runs", "rebuild_index", "register_run", "remove_index_entry", "search_runs", "verify_ledger", "verify_run",
]


def __getattr__(name: str):
    if name in {"RunRegistry", "rebuild_index", "verify_ledger", "register_run", "get_run", "list_runs", "search_runs", "verify_run", "remove_index_entry"}:
        from research_os.ledger.registry import RunRegistry, get_run, list_runs, rebuild_index, register_run, remove_index_entry, search_runs, verify_ledger, verify_run
        return {"RunRegistry": RunRegistry, "rebuild_index": rebuild_index, "verify_ledger": verify_ledger, "register_run": register_run, "get_run": get_run, "list_runs": list_runs, "search_runs": search_runs, "verify_run": verify_run, "remove_index_entry": remove_index_entry}[name]
    raise AttributeError(name)
