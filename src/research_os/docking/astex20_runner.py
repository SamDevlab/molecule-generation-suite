from __future__ import annotations

import json
from pathlib import Path
import platform

from research_os.docking import redocking as base
from research_os.docking import redocking_v12 as evaluator
from research_os.docking.astex20 import (
    BENCHMARK_ID,
    FROZEN_PROSPECTIVE_CASES,
    PREFLIGHT_ARTIFACT_ID,
    PREFLIGHT_RUN_ID,
    PREFLIGHT_SELECTION_MANIFEST_HASH,
    PROTOCOL_ID,
)
from research_os.docking.redocking_v12_identity import execution_hash, scientific_result_hash
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


HISTORICAL_REDOCK_002_PROTOCOL_ID = "research-os.redocking.holdout.v1.0"
HISTORICAL_REDOCK_002_SCIENTIFIC_RESULT_HASH = (
    "8540d1acf507047af402013f9d9d5d6ad93c5ac63123b95ab2876a46ecabb00c"
)
HISTORICAL_REDOCK_002_PASSING = 2
HISTORICAL_REDOCK_002_TOTAL = 5


def _descriptive_astex20(prospective_summary: dict[str, object]) -> dict[str, object]:
    """Combine historical and prospective <=2 Å counts for context only.

    ``passing_rmsd_cases`` in the shared redocking summary means that RMSD was
    successfully evaluated; it does *not* mean RMSD <= 2 Å. This descriptive
    aggregate therefore reads the threshold-specific count/denominator directly
    and uses explicit field names so technical PASS cannot be mistaken for
    pose-localization success again.
    """

    criterion = prospective_summary.get("pose_1_rmsd_le_2_angstrom")
    if not isinstance(criterion, dict):
        raise ValueError("prospective summary is missing the pose-1 <=2 Å criterion")

    prospective_successes = int(criterion["count"])
    prospective_total = int(criterion["denominator"])
    summary_total = int(prospective_summary["total_cases"])
    if prospective_total != summary_total:
        raise ValueError("prospective <=2 Å denominator does not match total_cases")
    if prospective_successes < 0 or prospective_successes > prospective_total:
        raise ValueError("prospective <=2 Å success count is outside its denominator")

    combined_successes = HISTORICAL_REDOCK_002_PASSING + prospective_successes
    combined_total = HISTORICAL_REDOCK_002_TOTAL + prospective_total
    return {
        "role": "descriptive-only; includes 5 previously observed REDOCK-002 cases",
        "criterion": "rank-1 same-frame RMSD <= 2 Å",
        "historical_pose_1_rmsd_le_2_count": HISTORICAL_REDOCK_002_PASSING,
        "historical_total_cases": HISTORICAL_REDOCK_002_TOTAL,
        "prospective_pose_1_rmsd_le_2_count": prospective_successes,
        "prospective_total_cases": prospective_total,
        "combined_pose_1_rmsd_le_2_count": combined_successes,
        "combined_total_cases": combined_total,
        "combined_fraction_pose_1_rmsd_le_2": combined_successes / combined_total,
    }


def run_frozen_astex20_prospective_benchmark(workdir: str | Path) -> dict[str, object]:
    """Execute only the frozen 15-case prospective REDOCK-003 extension."""

    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    vina = VinaEngine()
    obabel = OpenBabelEngine()

    records = [
        evaluator.run_redocking_case(case, root, vina=vina, obabel=obabel)
        for case in FROZEN_PROSPECTIVE_CASES
    ]
    result_objects = [
        base.RedockingCaseResult(
            case_id=str(record["result"]["case_id"]),
            status=str(record["result"]["status"]),
            pose_1_rmsd_angstrom=record["result"].get("pose_1_rmsd_angstrom"),
            minimum_rmsd_angstrom=record["result"].get("minimum_rmsd_angstrom"),
            pose_count=int(record["result"].get("pose_count", 0)),
            vina_pose_1_score_kcal_mol=record["result"].get("vina_pose_1_score_kcal_mol"),
            first_loss=record["result"].get("first_loss"),
        )
        for record in records
    ]

    summary = evaluator.summarize_redocking_results(result_objects)
    summary["evaluator_protocol_id"] = summary["protocol_id"]
    summary["protocol_id"] = PROTOCOL_ID
    summary["benchmark_id"] = BENCHMARK_ID
    summary["cohort_role"] = "prospective-primary"
    summary["preflight_selection_manifest_hash"] = PREFLIGHT_SELECTION_MANIFEST_HASH

    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "vina_version": vina.version,
        "openbabel_version": obabel.version,
        "vina_executable": vina.executable,
        "openbabel_executable": obabel.executable,
    }
    report: dict[str, object] = {
        "benchmark_id": BENCHMARK_ID,
        "protocol_id": PROTOCOL_ID,
        "evaluator_protocol_id": evaluator.PROTOCOL_ID,
        "symmetry_mapping_max_matches": evaluator.SYMMETRY_MAX_MATCHES,
        "preflight": {
            "run_id": PREFLIGHT_RUN_ID,
            "artifact_id": PREFLIGHT_ARTIFACT_ID,
            "selection_manifest_hash": PREFLIGHT_SELECTION_MANIFEST_HASH,
            "docking_executed_in_preflight": False,
        },
        "frozen_cases": [case.to_dict() for case in FROZEN_PROSPECTIVE_CASES],
        "records": records,
        "summary": summary,
        "historical_context": {
            "role": "context-only; excluded from prospective primary denominator",
            "benchmark_id": "REDOCK-002",
            "protocol_id": HISTORICAL_REDOCK_002_PROTOCOL_ID,
            "scientific_result_hash": HISTORICAL_REDOCK_002_SCIENTIFIC_RESULT_HASH,
            "passing_rmsd_cases": HISTORICAL_REDOCK_002_PASSING,
            "total_cases": HISTORICAL_REDOCK_002_TOTAL,
        },
        "descriptive_astex20": _descriptive_astex20(summary),
        "environment": environment,
    }
    stable_hash = scientific_result_hash(report)
    report["scientific_result_hash"] = stable_hash
    report["execution_hash"] = execution_hash(report, stable_hash)

    output = root / "redocking-astex20-result-v1.0.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return report
