"""Typed query facades over :class:`research_os.ledger.RunRegistry`."""

from __future__ import annotations

from typing import Any

from research_os.ledger.registry import RunRegistry


def search_runs(registry: RunRegistry, **filters: Any):
    return registry.search_runs(**filters)


def runs_using_dataset(registry: RunRegistry, dataset_id: str, **kwargs: Any):
    return registry.runs_using_dataset(dataset_id, **kwargs)


def datasets_used_by_run(registry: RunRegistry, run_id: str):
    return registry.datasets_used_by_run(run_id)


def runs_using_model(registry: RunRegistry, model_id: str):
    return registry.runs_using_model(model_id)


def model_lineage(registry: RunRegistry, model_id: str) -> dict[str, Any]:
    return {"model_id": model_id, "training_run_id": registry.training_run_for_model(model_id), "runs": [run.to_dict() for run in registry.runs_using_model(model_id)]}


def get_claim(registry: RunRegistry, claim_id: str):
    return registry.get_claim(claim_id)


def trace_claim(registry: RunRegistry, claim_id: str):
    return registry.trace_claim(claim_id)


def claims_from_run(registry: RunRegistry, run_id: str):
    return registry.claims_from_run(run_id)


def claims_by_status(registry: RunRegistry, status: str):
    return registry.claims_by_status(status)


def claims_by_evidence_level(registry: RunRegistry, level: str):
    return registry.claims_by_evidence_level(level)


def get_evidence(registry: RunRegistry, evidence_id: str):
    return registry.get_evidence(evidence_id)


def trace_evidence(registry: RunRegistry, evidence_id: str):
    return registry.trace_evidence(evidence_id)


def evidence_from_run(registry: RunRegistry, run_id: str):
    return registry.evidence_from_run(run_id)


def evidence_by_level(registry: RunRegistry, level: str):
    return registry.evidence_by_level(level)


def evidence_by_kind(registry: RunRegistry, kind: str):
    return registry.evidence_by_kind(kind)
