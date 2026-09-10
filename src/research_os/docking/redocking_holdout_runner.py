from __future__ import annotations

import json
from pathlib import Path
import platform

from research_os.docking import redocking as v11
from research_os.docking import redocking_v12 as evaluator
from research_os.docking.redocking_holdout import FROZEN_HOLDOUT_CASES, PROTOCOL_ID
from research_os.docking.redocking_v12_identity import execution_hash, scientific_result_hash
from research_os.engines.openbabel import OpenBabelEngine
from research_os.engines.vina import VinaEngine


def run_frozen_holdout_benchmark(workdir: str | Path) -> dict[str, object]:
    """Execute REDOCK-002 with the already-frozen REDOCK-001 v1.2 method.

    REDOCK-002 has its own benchmark protocol identity, but intentionally reuses
    the validated v1.2 case executor/evaluator unchanged. This prevents the
    holdout from acquiring a second implementation path that could drift from
    the method it is supposed to test for generalization.
    """

    root = Path(workdir)
    root.mkdir(parents=True, exist_ok=True)
    vina = VinaEngine()
    obabel = OpenBabelEngine()

    records = [
        evaluator.run_redocking_case(case, root, vina=vina, obabel=obabel)
        for case in FROZEN_HOLDOUT_CASES
    ]
    result_objects = [
        v11.RedockingCaseResult(
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

    environment = {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "vina_version": vina.version,
        "openbabel_version": obabel.version,
        "vina_executable": vina.executable,
        "openbabel_executable": obabel.executable,
    }
    report: dict[str, object] = {
        "protocol_id": PROTOCOL_ID,
        "evaluator_protocol_id": evaluator.PROTOCOL_ID,
        "symmetry_mapping_max_matches": evaluator.SYMMETRY_MAX_MATCHES,
        "frozen_cases": [case.to_dict() for case in FROZEN_HOLDOUT_CASES],
        "records": records,
        "summary": summary,
        "environment": environment,
    }
    stable_hash = scientific_result_hash(report)
    report["scientific_result_hash"] = stable_hash
    report["execution_hash"] = execution_hash(report, stable_hash)

    output = root / "redocking-holdout-result-v1.0.json"
    output.write_text(json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True), encoding="utf-8")
    return report
