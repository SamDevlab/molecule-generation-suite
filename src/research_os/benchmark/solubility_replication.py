"""Multi-seed replication layer for ONLINE-EXP-001."""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from statistics import mean, stdev
from typing import Any, Mapping, Sequence

from research_os.benchmark.solubility import (
    EXPERIMENT_ID,
    PROTOCOL_VERSION,
    SolubilityRecord,
    dataset_hash,
    run_solubility_benchmark,
)
from research_os.core.hashing import sha256_json


REPLICATION_ID = f"{EXPERIMENT_ID}-REPLICATION"
DEFAULT_SEEDS = (7, 21, 42, 84, 101)


@dataclass(frozen=True)
class MetricSummary:
    n: int
    mean: float
    stdev: float | None
    minimum: float
    maximum: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "n": self.n,
            "mean": self.mean,
            "stdev": self.stdev,
            "min": self.minimum,
            "max": self.maximum,
        }


def summarize(values: Sequence[float]) -> MetricSummary:
    numbers = tuple(float(value) for value in values)
    if not numbers:
        raise ValueError("metric summary requires at least one value")
    return MetricSummary(
        n=len(numbers),
        mean=mean(numbers),
        stdev=stdev(numbers) if len(numbers) >= 2 else None,
        minimum=min(numbers),
        maximum=max(numbers),
    )


@dataclass(frozen=True)
class ReplicatedModelSummary:
    model: str
    random_mae: MetricSummary
    random_rmse: MetricSummary
    random_r2: MetricSummary
    scaffold_mae: MetricSummary
    scaffold_rmse: MetricSummary
    scaffold_r2: MetricSummary
    rmse_generalization_gap: MetricSummary

    def to_dict(self) -> dict[str, Any]:
        return {
            "model": self.model,
            "random": {
                "MAE": self.random_mae.to_dict(),
                "RMSE": self.random_rmse.to_dict(),
                "R2": self.random_r2.to_dict(),
            },
            "scaffold": {
                "MAE": self.scaffold_mae.to_dict(),
                "RMSE": self.scaffold_rmse.to_dict(),
                "R2": self.scaffold_r2.to_dict(),
            },
            "rmse_generalization_gap": self.rmse_generalization_gap.to_dict(),
        }


@dataclass(frozen=True)
class SolubilityReplicationReport:
    replication_id: str
    protocol_version: str
    dataset_hash: str
    record_count: int
    seeds: tuple[int, ...]
    run_report_hashes: tuple[str, ...]
    models: tuple[ReplicatedModelSummary, ...]
    notes: tuple[str, ...]

    @property
    def report_hash(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        return {
            "replication_id": self.replication_id,
            "protocol_version": self.protocol_version,
            "dataset_hash": self.dataset_hash,
            "record_count": self.record_count,
            "seeds": list(self.seeds),
            "run_report_hashes": list(self.run_report_hashes),
            "models": [item.to_dict() for item in self.models],
            "notes": list(self.notes),
        }

    def to_dict(self) -> dict[str, Any]:
        return {**self._payload(), "report_hash": self.report_hash}

    def write(self, path: str | Path) -> str:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False), encoding="utf-8")
        return str(target)


def _model_maps(run: Any) -> dict[str, dict[str, Any]]:
    return {
        split.strategy: {model.model: model for model in split.models}
        for split in run.splits
    }


def run_solubility_replication(
    records: Sequence[SolubilityRecord],
    *,
    seeds: Sequence[int] = DEFAULT_SEEDS,
) -> SolubilityReplicationReport:
    selected_seeds = tuple(int(seed) for seed in seeds)
    if len(selected_seeds) < 2:
        raise ValueError("multi-seed replication requires at least two seeds")
    if len(set(selected_seeds)) != len(selected_seeds):
        raise ValueError("replication seeds must be unique")

    runs = tuple(run_solubility_benchmark(records, seed=seed) for seed in selected_seeds)
    expected_hash = dataset_hash(records)
    if any(run.dataset_hash != expected_hash for run in runs):
        raise RuntimeError("dataset hash changed across replication runs")

    mappings = tuple(_model_maps(run) for run in runs)
    model_names = tuple(model.model for model in runs[0].splits[0].models)
    summaries: list[ReplicatedModelSummary] = []
    for model_name in model_names:
        random_models = tuple(mapping["random"][model_name] for mapping in mappings)
        scaffold_models = tuple(mapping["scaffold"][model_name] for mapping in mappings)
        summaries.append(
            ReplicatedModelSummary(
                model=model_name,
                random_mae=summarize([item.test_metrics.mae for item in random_models]),
                random_rmse=summarize([item.test_metrics.rmse for item in random_models]),
                random_r2=summarize([item.test_metrics.r2 for item in random_models]),
                scaffold_mae=summarize([item.test_metrics.mae for item in scaffold_models]),
                scaffold_rmse=summarize([item.test_metrics.rmse for item in scaffold_models]),
                scaffold_r2=summarize([item.test_metrics.r2 for item in scaffold_models]),
                rmse_generalization_gap=summarize(
                    [
                        scaffold.test_metrics.rmse - random.test_metrics.rmse
                        for scaffold, random in zip(scaffold_models, random_models)
                    ]
                ),
            )
        )

    return SolubilityReplicationReport(
        replication_id=REPLICATION_ID,
        protocol_version=f"{PROTOCOL_VERSION}.multi-seed-v1",
        dataset_hash=expected_hash,
        record_count=len(records),
        seeds=selected_seeds,
        run_report_hashes=tuple(run.report_hash for run in runs),
        models=tuple(summaries),
        notes=(
            "The same fixed model hyperparameters are reused for every seed; no seed-specific tuning occurs.",
            "Reported dispersion reflects partition-seed sensitivity on this dataset, not experimental measurement uncertainty.",
            "A positive mean RMSE generalization gap indicates worse scaffold-held-out error on average.",
        ),
    )
