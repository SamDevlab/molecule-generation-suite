"""Failure analysis for real molecular models."""

from __future__ import annotations

from collections import defaultdict
from math import sqrt
from typing import Any, Mapping, Sequence

from research_os.campaigns.models import ModelFailureAnalysis


def _stats(items: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    if not items:
        return {"sample_count": 0, "mae": None, "rmse": None, "bias": None, "ood_fraction": None, "uncertainty_coverage": None}
    errors = [float(item["prediction"]) - float(item["actual"]) for item in items]
    intervals = [item.get("interval") for item in items]
    valid_intervals = [interval for interval in intervals if isinstance(interval, (list, tuple)) and len(interval) == 2]
    coverage = sum(float(interval[0]) <= float(item["actual"]) <= float(interval[1]) for item, interval in zip(items, intervals) if isinstance(interval, (list, tuple)) and len(interval) == 2) / len(valid_intervals) if valid_intervals else None
    return {"sample_count": len(items), "mae": sum(abs(error) for error in errors) / len(errors), "rmse": sqrt(sum(error * error for error in errors) / len(errors)), "bias": sum(errors) / len(errors), "ood_fraction": sum(bool(item.get("ood")) for item in items) / len(items), "uncertainty_coverage": coverage}


def analyze_model_failures(real_ml_result: Any, records: Sequence[Mapping[str, Any]]) -> ModelFailureAnalysis:
    by_id = {str(record.get("compound_id") or record.get("ID") or record.get("id")): record for record in records}
    rows: list[dict[str, Any]] = []
    for prediction in real_ml_result.test_predictions:
        # RealMLResult intentionally keeps prediction provenance but the split
        # IDs are the authoritative join to actual held-out records.
        rows.append({"id": None, "prediction": prediction.prediction, "ood": not prediction.in_domain, "interval": prediction.prediction_interval, "status": prediction.status})
    test_ids = tuple(real_ml_result.split.test_ids)
    for row, record_id in zip(rows, test_ids):
        row["id"] = str(record_id)
        record = by_id.get(str(record_id), {})
        row["actual"] = float(record.get("target", record.get("Solubility")))
        row["smiles"] = record.get("smiles", record.get("SMILES"))
        row["molecular_weight"] = record.get("molecular_weight")
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        groups["all"].append(row)
        weight = row.get("molecular_weight")
        if weight is not None:
            try:
                numeric = float(weight)
                groups["molecular_weight<=200" if numeric <= 200 else "molecular_weight>200"].append(row)
            except (TypeError, ValueError):
                pass
        groups["ood" if row["ood"] else "in_domain"].append(row)
    notable = []
    for row in sorted(rows, key=lambda item: abs(float(item["prediction"]) - float(item["actual"])), reverse=True)[:5]:
        notable.append({"id": row["id"], "actual": row["actual"], "prediction": row["prediction"], "error": row["prediction"] - row["actual"], "ood": row["ood"], "status": row["status"]})
    return ModelFailureAnalysis(
        analysis_id="MFA-" + str(real_ml_result.model_artifact.model_id),
        model_id=real_ml_result.model_artifact.model_id,
        dataset_id=real_ml_result.dataset.dataset_id,
        split_id=real_ml_result.split.split_id,
        overall=_stats(groups["all"]),
        segments=tuple({"segment": name, **_stats(values)} for name, values in sorted(groups.items()) if name != "all"),
        notable_failures=tuple(notable),
        ood_policy="OUT_OF_DOMAIN predictions retained for audit and excluded from normal ranking.",
        uncertainty_policy="Residual-calibrated intervals are reported as observed coverage, not certainty.",
    )
