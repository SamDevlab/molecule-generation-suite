"""MOLDISC-007: operational fallback seed selection from frozen prior evidence."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Any, Mapping, Sequence

from research_os.core.hashing import sha256_json


PROGRAM_ID = "MOLDISC-007"
COVERAGE_BOUNDARY = 0.4
RANK1_RMSD_THRESHOLD_ANGSTROM = 2.0
EXPECTED_CASE_IDS = ("ATX-014", "ATX-007", "ATX-013", "ATX-012")


class MOLDISC007Error(RuntimeError):
    """Fail-closed error for fallback-selection identity or rule drift."""


@dataclass(frozen=True)
class FallbackCandidate:
    case_id: str
    pdb_id: str
    chem_comp_id: str
    target: str
    aqsoldb_nearest_similarity: float
    redock_pose_1_rmsd_angstrom: float
    redock_rank_1_success: bool
    operationally_blocked: bool
    block_reason: str | None

    @property
    def eligible(self) -> bool:
        return (
            self.aqsoldb_nearest_similarity >= COVERAGE_BOUNDARY
            and not self.operationally_blocked
            and self.redock_rank_1_success
            and self.redock_pose_1_rmsd_angstrom <= RANK1_RMSD_THRESHOLD_ANGSTROM
        )

    def to_dict(self) -> dict[str, Any]:
        return {**asdict(self), "eligible": self.eligible}


@dataclass(frozen=True)
class FallbackSelection:
    selected_case_id: str | None
    selected_pdb_id: str | None
    selected_chem_comp_id: str | None
    selected_target: str | None
    selected_aqsoldb_nearest_similarity: float | None
    eligible_case_ids: tuple[str, ...]
    coverage_boundary: float = COVERAGE_BOUNDARY
    rank1_rmsd_threshold_angstrom: float = RANK1_RMSD_THRESHOLD_ANGSTROM

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["eligible_case_ids"] = list(self.eligible_case_ids)
        return value


@dataclass(frozen=True)
class MOLDISC007Result:
    program_id: str
    config_hash: str
    candidates: tuple[FallbackCandidate, ...]
    selection: FallbackSelection
    program_scientific_hash: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "program_id": self.program_id,
            "config_hash": self.config_hash,
            "candidates": [item.to_dict() for item in self.candidates],
            "selection": self.selection.to_dict(),
            "program_scientific_hash": self.program_scientific_hash,
        }


def load_program_config_v7(path: str | Path) -> dict[str, Any]:
    config = json.loads(Path(path).read_text(encoding="utf-8"))
    if config.get("program_id") != PROGRAM_ID or config.get("program_version") != "1.0":
        raise MOLDISC007Error("MOLDISC-007 requires frozen program_id/version 1.0")

    parent = config.get("parent_evidence") or {}
    expected_parent = {
        "moldisc_003_program_scientific_hash": "977428ab62ff38cda8033f5daf9ecc85e93f9f9994240ca2f13729405ab58e2b",
        "redock_003_scientific_result_hash": "e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762",
        "moldisc_006_merge_commit": "464ab97017439caf6c8de75ef2aad42f11b2cf03",
        "moldisc_006_status": "CLOSED_INDETERMINATE_TARGET_PREPARATION",
    }
    for key, value in expected_parent.items():
        if parent.get(key) != value:
            raise MOLDISC007Error(f"MOLDISC-007 parent evidence field {key!r} drifted")

    candidates = config.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 4:
        raise MOLDISC007Error("MOLDISC-007 requires exactly four frozen MOLDISC-003 eligible seeds")
    case_ids = tuple(str(item.get("case_id") or "") for item in candidates)
    if case_ids != EXPECTED_CASE_IDS:
        raise MOLDISC007Error(
            f"MOLDISC-007 candidate order/identity drifted: expected {EXPECTED_CASE_IDS}, got {case_ids}"
        )

    rule = config.get("selection_rule") or {}
    if float(rule.get("aqsoldb_eligibility_boundary", -1)) != COVERAGE_BOUNDARY:
        raise MOLDISC007Error("MOLDISC-007 AqSolDB boundary drifted")
    if float(rule.get("require_redock_rank_1_rmsd_lte_angstrom", -1)) != RANK1_RMSD_THRESHOLD_ANGSTROM:
        raise MOLDISC007Error("MOLDISC-007 REDOCK rank-1 RMSD threshold drifted")
    if rule.get("require_not_operationally_blocked") is not True:
        raise MOLDISC007Error("MOLDISC-007 must exclude operationally blocked targets")
    if rule.get("post_result_rule_changes_allowed") is not False:
        raise MOLDISC007Error("MOLDISC-007 forbids post-result rule changes")

    blocked = [item for item in candidates if item.get("operationally_blocked")]
    if len(blocked) != 1 or blocked[0].get("case_id") != "ATX-014":
        raise MOLDISC007Error("MOLDISC-007 must preserve only ATX-014 as the MOLDISC-006 blocked target")
    return config


def _candidate(raw: Mapping[str, Any]) -> FallbackCandidate:
    return FallbackCandidate(
        case_id=str(raw["case_id"]),
        pdb_id=str(raw["pdb_id"]),
        chem_comp_id=str(raw["chem_comp_id"]),
        target=str(raw["target"]),
        aqsoldb_nearest_similarity=float(raw["aqsoldb_nearest_similarity"]),
        redock_pose_1_rmsd_angstrom=float(raw["redock_pose_1_rmsd_angstrom"]),
        redock_rank_1_success=bool(raw["redock_rank_1_success"]),
        operationally_blocked=bool(raw["operationally_blocked"]),
        block_reason=(str(raw["block_reason"]) if raw.get("block_reason") is not None else None),
    )


def select_operational_fallback(candidates: Sequence[FallbackCandidate]) -> FallbackSelection:
    eligible = [item for item in candidates if item.eligible]
    eligible.sort(key=lambda item: (-item.aqsoldb_nearest_similarity, item.case_id))
    if not eligible:
        return FallbackSelection(
            selected_case_id=None,
            selected_pdb_id=None,
            selected_chem_comp_id=None,
            selected_target=None,
            selected_aqsoldb_nearest_similarity=None,
            eligible_case_ids=(),
        )
    selected = eligible[0]
    return FallbackSelection(
        selected_case_id=selected.case_id,
        selected_pdb_id=selected.pdb_id,
        selected_chem_comp_id=selected.chem_comp_id,
        selected_target=selected.target,
        selected_aqsoldb_nearest_similarity=selected.aqsoldb_nearest_similarity,
        eligible_case_ids=tuple(item.case_id for item in eligible),
    )


def run_moldisc_007(*, config_path: str | Path, output_root: str | Path) -> MOLDISC007Result:
    config = load_program_config_v7(config_path)
    config_hash = sha256_json(config)
    candidates = tuple(_candidate(item) for item in config["candidates"])
    selection = select_operational_fallback(candidates)
    scientific = {
        "program_id": PROGRAM_ID,
        "config_hash": config_hash,
        "candidates": [item.to_dict() for item in candidates],
        "selection": selection.to_dict(),
    }
    result = MOLDISC007Result(
        program_id=PROGRAM_ID,
        config_hash=config_hash,
        candidates=candidates,
        selection=selection,
        program_scientific_hash=sha256_json(scientific),
    )

    root = Path(output_root)
    root.mkdir(parents=True, exist_ok=False)
    (root / "program_manifest.json").write_text(
        json.dumps(result.to_dict(), indent=2, sort_keys=True, ensure_ascii=False),
        encoding="utf-8",
    )
    (root / "selection.json").write_text(
        json.dumps(
            {
                "selection": selection.to_dict(),
                "candidate_evidence": [item.to_dict() for item in candidates],
            },
            indent=2,
            sort_keys=True,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (root / "program_report.md").write_text(_markdown(config, result), encoding="utf-8")
    return result


def _markdown(config: Mapping[str, Any], result: MOLDISC007Result) -> str:
    lines = [
        "# MOLDISC-007 — operational fallback seed selection",
        "",
        f"- Program scientific hash: {result.program_scientific_hash}",
        f"- AqSolDB coverage boundary: {COVERAGE_BOUNDARY}",
        f"- REDOCK rank-1 RMSD threshold: <= {RANK1_RMSD_THRESHOLD_ANGSTROM} Å",
        "",
        "## Frozen candidate evidence",
        "",
        "| Case | PDB | Ligand | AqSolDB nearest | REDOCK pose-1 RMSD (Å) | blocked | eligible |",
        "|---|---|---|---:|---:|---|---|",
    ]
    for item in result.candidates:
        lines.append(
            f"| {item.case_id} | {item.pdb_id} | {item.chem_comp_id} | "
            f"{item.aqsoldb_nearest_similarity:.6f} | {item.redock_pose_1_rmsd_angstrom:.3f} | "
            f"{'YES' if item.operationally_blocked else 'NO'} | {'YES' if item.eligible else 'NO'} |"
        )
    lines.extend(["", "## Selection", ""])
    if result.selection.selected_case_id is None:
        lines.append("No fallback seed met all frozen operational and coverage requirements.")
    else:
        lines.append(
            f"Selected fallback seed: {result.selection.selected_case_id} / "
            f"{result.selection.selected_pdb_id} / {result.selection.selected_chem_comp_id} / "
            f"{result.selection.selected_target}, AqSolDB nearest similarity "
            f"{result.selection.selected_aqsoldb_nearest_similarity:.6f}."
        )
    lines.extend(["", "## Interpretation boundaries", ""])
    lines.extend(f"- {item}" for item in config["interpretation_boundaries"])
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "COVERAGE_BOUNDARY",
    "FallbackCandidate",
    "FallbackSelection",
    "MOLDISC007Error",
    "MOLDISC007Result",
    "PROGRAM_ID",
    "RANK1_RMSD_THRESHOLD_ANGSTROM",
    "load_program_config_v7",
    "run_moldisc_007",
    "select_operational_fallback",
]
