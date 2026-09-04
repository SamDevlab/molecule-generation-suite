"""Replicated docking campaigns with deterministic aggregation."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from statistics import mean, median, pstdev
from typing import Any
import uuid

from research_os.core.types import EvidenceLevel


@dataclass(frozen=True)
class DockingCampaignResult:
    campaign_id: str
    target_id: str | None
    ligand_id: str | None
    replicate_count: int
    seeds: tuple[int, ...]
    run_ids: tuple[str, ...]
    scores_kcal_mol: tuple[float, ...]
    best_score_kcal_mol: float | None
    median_score_kcal_mol: float | None
    mean_score_kcal_mol: float | None
    std_score_kcal_mol: float | None
    aggregation_protocol: str
    status: str
    evidence_level: str = EvidenceLevel.E2_COMPUTATIONAL.value
    run_manifests: tuple[Any, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {key: list(value) if isinstance(value, tuple) else value for key, value in self.__dict__.items() if key != "run_manifests"}


@dataclass
class DockingCampaign:
    campaign_id: str = field(default_factory=lambda: f"CAMP-{uuid.uuid4().hex[:12].upper()}")
    target_id: str | None = None
    ligand_id: str | None = None
    replicate_count: int = 3
    seed_base: int = 42
    aggregation_protocol: str = "best/median/mean/std over independent seeded runs v1"

    def run(self, lab: Any, request: dict[str, Any]) -> DockingCampaignResult:
        if self.replicate_count < 1:
            raise ValueError("replicate_count must be positive")
        runs, scores = [], []
        seeds = tuple(self.seed_base + index for index in range(self.replicate_count))
        for seed in seeds:
            payload = dict(request)
            payload["seed"] = seed
            if payload.get("output_path") is None and payload.get("ligand_path"):
                ligand = Path(str(payload["ligand_path"]))
                payload["output_path"] = str(ligand.with_name(f"{ligand.stem}_seed{seed}_docked.pdbqt"))
            if self.target_id is not None: payload["target_id"] = self.target_id
            run = lab.run(payload, experiment="vina_docking_campaign_replicate")
            runs.append(run)
            evidence = next((item for item in reversed(run.evidence) if item.kind == "molecular_docking_result"), None)
            score = evidence.payload.get("best_affinity_kcal_mol") if evidence else None
            if isinstance(score, (int, float)): scores.append(float(score))
        passed = len(scores) == self.replicate_count and all(getattr(run, "passed", False) for run in runs)
        return DockingCampaignResult(self.campaign_id, self.target_id or request.get("target_id"), self.ligand_id, self.replicate_count, seeds, tuple(run.run_id for run in runs), tuple(scores), min(scores) if scores else None, median(scores) if scores else None, mean(scores) if scores else None, pstdev(scores) if len(scores) > 1 else 0.0 if scores else None, self.aggregation_protocol, "SUPPORTED_AND_EXECUTED" if passed else "INDETERMINATE", run_manifests=tuple(runs))
