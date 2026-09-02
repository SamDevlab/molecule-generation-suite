from __future__ import annotations

from dataclasses import asdict, dataclass, field
from enum import Enum
from typing import Any, Callable
import copy

from research_os.core.hashing import sha256_json
from research_os.core.types import RunLineage, RunManifest


class ReproducibilityStatus(str, Enum):
    REPRODUCED = "REPRODUCED"
    REPRODUCED_WITH_ENVIRONMENT_CHANGE = "REPRODUCED_WITH_ENVIRONMENT_CHANGE"
    DIVERGED = "DIVERGED"
    NOT_COMPARABLE = "NOT_COMPARABLE"
    INDETERMINATE = "INDETERMINATE"


@dataclass(frozen=True)
class RunComparison:
    original_run_id: str
    rerun_id: str
    status: ReproducibilityStatus
    same_inputs: bool | None
    same_config: bool | None
    same_dataset_hashes: bool | None
    same_code_commit: bool | None
    same_environment: bool | None
    same_evidence_values: bool | None
    same_claims: bool | None
    differences: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["status"] = self.status.value
        data["differences"] = list(self.differences)
        return data


def rerun(
    reference_run: RunManifest,
    runner: Any,
    *,
    reuse_inputs: bool = True,
    reuse_config: bool = True,
    environment: Any | None = None,
) -> RunManifest:
    """Execute a fresh run and record lineage without modifying the reference."""
    if reference_run.sealed is False and reference_run.lifecycle.value == "CREATED":
        raise ValueError("reference run must have started before it can be rerun")
    inputs = copy.deepcopy(dict(reference_run.inputs)) if reuse_inputs else {}
    if hasattr(runner, "run"):
        new_run = runner.run(inputs, experiment=reference_run.experiment)
    elif callable(runner):
        new_run = runner(inputs, reference_run.experiment)
    else:
        raise TypeError("runner must be a Lab-like object or callable")
    if not isinstance(new_run, RunManifest):
        raise TypeError("rerun runner must return RunManifest")
    if new_run.run_id == reference_run.run_id:
        raise ValueError("rerun must produce a new run_id")
    if reuse_config:
        new_run.config.update(copy.deepcopy(dict(reference_run.config)))
    for manifest in reference_run.dataset_manifests:
        new_run.attach_dataset(manifest)
    if environment is None:
        from research_os.environment import capture_environment
        environment = capture_environment()
    new_run.attach_environment(environment)
    object.__setattr__(new_run, "lineage", RunLineage(parent_run_id=reference_run.run_id, rerun_of=reference_run.run_id, derived_from=(reference_run.run_id,)))
    return new_run


def compare_runs(original: RunManifest, rerun_run: RunManifest) -> RunComparison:
    same_inputs = sha256_json(dict(original.inputs)) == sha256_json(dict(rerun_run.inputs))
    same_config = sha256_json(dict(original.config)) == sha256_json(dict(rerun_run.config))
    original_datasets = tuple(getattr(item, "sha256", None) for item in original.dataset_manifests)
    rerun_datasets = tuple(getattr(item, "sha256", None) for item in rerun_run.dataset_manifests)
    same_dataset_hashes: bool | None = original_datasets == rerun_datasets if original_datasets or rerun_datasets else True
    original_commit = _environment_value(original, "git", "commit")
    rerun_commit = _environment_value(rerun_run, "git", "commit")
    same_code_commit: bool | None = original_commit == rerun_commit if original_commit and rerun_commit else None
    original_environment = getattr(original.environment_manifest, "environment_hash", None)
    rerun_environment = getattr(rerun_run.environment_manifest, "environment_hash", None)
    same_environment: bool | None = original_environment == rerun_environment if original_environment and rerun_environment else None
    same_evidence_values = _evidence_values(original) == _evidence_values(rerun_run)
    same_claims = _claims_values(original) == _claims_values(rerun_run)
    differences = tuple(name for name, value in (("inputs", same_inputs), ("config", same_config), ("dataset_hashes", same_dataset_hashes), ("code_commit", same_code_commit), ("environment", same_environment), ("evidence_values", same_evidence_values), ("claims", same_claims)) if value is False)
    if not same_inputs or not same_config or same_dataset_hashes is False or same_code_commit is False or not same_evidence_values or not same_claims:
        status = ReproducibilityStatus.DIVERGED
    elif same_environment is False:
        status = ReproducibilityStatus.REPRODUCED_WITH_ENVIRONMENT_CHANGE
    elif same_code_commit is None or same_environment is None:
        status = ReproducibilityStatus.NOT_COMPARABLE
    else:
        status = ReproducibilityStatus.REPRODUCED
    return RunComparison(original.run_id, rerun_run.run_id, status, same_inputs, same_config, same_dataset_hashes, same_code_commit, same_environment, same_evidence_values, same_claims, differences)


def _environment_value(run: RunManifest, section: str, key: str) -> Any:
    manifest = run.environment_manifest
    values = getattr(manifest, section, None) if manifest is not None else None
    return values.get(key) if isinstance(values, dict) else None


def _evidence_values(run: RunManifest) -> str:
    values = []
    for evidence in run.evidence:
        data = asdict(evidence)
        data.pop("evidence_id", None)
        data.pop("created_at", None)
        data["level"] = evidence.level.value
        values.append(data)
    return sha256_json(values)


def _claims_values(run: RunManifest) -> str:
    values = []
    for claim in run.claims:
        data = claim.to_dict() if hasattr(claim, "to_dict") else claim
        data = dict(data)
        data.pop("claim_id", None)
        values.append(data)
    return sha256_json(values)
