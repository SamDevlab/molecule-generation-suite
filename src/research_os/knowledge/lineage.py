"""Queries that join reviewed source records to immutable ledger bundles."""

from __future__ import annotations

from pathlib import Path
import json
from typing import Any


def _json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return default


def _source_ids(record: Any) -> set[str]:
    root = Path(record.bundle_path)
    values: set[str] = set()
    for item in _json(root / "provenance" / "sources.json", []):
        if isinstance(item, dict) and item.get("source_id"):
            values.add(str(item["source_id"]))
        if isinstance(item, dict) and item.get("provenance_id"):
            values.add(str(item["provenance_id"]))
    for item in _json(root / "evidence" / "evidence.json", []):
        if isinstance(item, dict):
            payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
            if payload.get("source_id"):
                values.add(str(payload["source_id"]))
    return values


def runs_from_source(registry: Any, source_id: str) -> list[Any]:
    return [record for record in registry.list_runs(limit=1_000_000) if source_id in _source_ids(record)]


def claims_from_source(registry: Any, source_id: str) -> list[Any]:
    return [claim for record in runs_from_source(registry, source_id) for claim in registry.claims_from_run(record.run_id)]


def evidence_from_source(registry: Any, source_id: str) -> list[Any]:
    return [evidence for record in runs_from_source(registry, source_id) for evidence in registry.evidence_from_run(record.run_id)]


def sources_for_claim(registry: Any, claim_id: str) -> list[dict[str, Any]]:
    trace = registry.trace_claim(claim_id)
    run = trace["run"]
    return _json(Path(run["bundle_path"]) / "provenance" / "sources.json", [])


def source_lineage(registry: Any, source_id: str) -> dict[str, Any]:
    runs = runs_from_source(registry, source_id)
    return {"source_id": source_id, "runs": [item.to_dict() for item in runs], "claims": [item.to_dict() for item in claims_from_source(registry, source_id)], "evidence": [item.to_dict() for item in evidence_from_source(registry, source_id)]}

