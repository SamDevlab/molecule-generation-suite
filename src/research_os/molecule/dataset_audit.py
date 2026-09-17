from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from pathlib import Path
from statistics import fmean
from typing import Any

from research_os.core.hashing import sha256_file
from research_os.molecule.legacy import LegacyFormolecularAdapter, LEGACY_DETERMINISTIC_COLUMNS


@dataclass(frozen=True)
class ColumnAuditSummary:
    count: int
    mean_absolute_difference: float | None
    max_absolute_difference: float | None


@dataclass(frozen=True)
class LegacyDatasetAuditReport:
    dataset_path: str
    dataset_hash: str
    rows_seen: int
    rows_with_valid_structure: int
    invalid_structures: int
    compared_columns: dict[str, ColumnAuditSummary]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def audit_legacy_csv(path: str | Path, limit: int | None = 10_000) -> LegacyDatasetAuditReport:
    """Read-only streaming audit of legacy deterministic molecular columns."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(source)
    adapter = LegacyFormolecularAdapter()
    differences: dict[str, list[float]] = {name: [] for name in LEGACY_DETERMINISTIC_COLUMNS}
    rows_seen = valid = invalid = 0
    with source.open("r", encoding="utf-8-sig", newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            if limit is not None and rows_seen >= limit:
                break
            rows_seen += 1
            try:
                findings = adapter.audit_deterministic_columns(row)
            except Exception:
                invalid += 1
                continue
            valid += 1
            for item in findings:
                differences[item.legacy_column].append(item.absolute_difference)
    summaries = {}
    for name, values in differences.items():
        if values:
            summaries[name] = ColumnAuditSummary(count=len(values), mean_absolute_difference=float(fmean(values)), max_absolute_difference=float(max(values)))
    return LegacyDatasetAuditReport(dataset_path=str(source), dataset_hash=sha256_file(source), rows_seen=rows_seen, rows_with_valid_structure=valid, invalid_structures=invalid, compared_columns=summaries)
