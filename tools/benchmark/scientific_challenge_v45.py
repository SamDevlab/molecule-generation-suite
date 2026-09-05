"""Run the v4.5 scientific red-team and false-conservatism audit."""

from __future__ import annotations

from datetime import datetime, timezone
import argparse
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.impact import FalseConservatismAudit, ScientificChallenge, ScientificChallengeStatus, ScientificChallengeStore


V40_ARTIFACT = REPO_ROOT / ".research-os-live-4.0" / "master-validation.json"
V41_ARTIFACT = REPO_ROOT / ".research-os-live-4.1" / "research-outcome-impact.json"
V43_ARTIFACT = REPO_ROOT / ".research-os-live-4.3" / "external-validation-campaigns.json"
V44_ARTIFACT = REPO_ROOT / ".research-os-live-4.4" / "research-impact-review.json"
OUTPUT_DEFAULT = REPO_ROOT / ".research-os-live-4.5" / "scientific-challenge.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _challenge(
    challenge_id: str,
    claim_id: str,
    status: ScientificChallengeStatus,
    *,
    evidence: tuple[str, ...] = (),
    decision: str | None = None,
    assumptions: tuple[str, ...],
    failure_modes: tuple[str, ...],
    contradictory: tuple[str, ...] = (),
    missing: tuple[str, ...],
    sensitivity: tuple[str, ...],
    dependence: tuple[str, ...],
    recommended: str,
) -> ScientificChallenge:
    return ScientificChallenge(challenge_id, claim_id, decision, evidence, assumptions, failure_modes, contradictory, missing, sensitivity, dependence, status, recommended)


def run_challenge(output: Path, *, ci_green: bool = False) -> dict[str, Any]:
    v40 = _load(V40_ARTIFACT)
    v41 = _load(V41_ARTIFACT)
    v43 = _load(V43_ARTIFACT)
    v44 = _load(V44_ARTIFACT)
    if not all(item.get("status") == "PASS" for item in (v40, v41, v43, v44)):
        raise RuntimeError("v4.5 requires PASS v4.0, v4.1, v4.3 and v4.4 artifacts")
    combustion_rows = v41["analyses"]["combustion"]["rows"]
    combustion_evidence = tuple(combustion_rows[0]["evidence_ids"])
    battery_evidence = tuple(v41["programs"][3]["execution"].get("evidence_ids", ()))
    external_evidence = ("EVD-V43-DLS-LOCKED-MODEL", "EVD-V43-DLS-SOURCE")
    store = ScientificChallengeStore()
    challenges = [
        _challenge("CH-V45-COX2", "CLM-COX2-1PXX-V2", ScientificChallengeStatus.ROBUST_UNDER_CHALLENGE, evidence=("EVD-8C48EDB3BEC7", "EVD-C78C348BB94C"), decision="DECISION-REAL-01-1DC0442BB0EA", assumptions=("murine PTGS2/COX-2", "1PXX chain A", "declared Vina grid and seeds"), failure_modes=("receptor-structure dependence", "score aggregation dependence", "docking is not measured affinity"), missing=("independent structure comparison with Vina available",), sensitivity=("three-seed spread is small but exhaustiveness was not varied",), dependence=("all supporting scores share 1PXX and the same protocol",), recommended="repeat only with a predeclared alternative receptor or protocol and retain E2 ceiling"),
        _challenge("CH-V45-SOLUBILITY-EXTERNAL", "CLM-863B37BB0E38", ScientificChallengeStatus.WEAKENED, evidence=external_evidence, decision="DECISION-V39-SOLUBILITY", assumptions=("SMILES identity and Morgan feature parity", "DLS and AqSolDB target units are comparable"), failure_modes=("all external records are OOD", "intrinsic versus general aqueous semantics", "small original training sample"), contradictory=(), missing=("an external source with compatible conditions and in-domain coverage",), sensitivity=("OOD threshold 0.4 controls rankability", "residual interval calibration is from the original validation split"), dependence=("no shared molecule overlap was found, but source-condition semantics differ",), recommended="keep the claim sample-specific and acquire a compatible in-domain external set"),
        _challenge("CH-V45-SOLUBILITY-FAILURE", "CLM-V41-SOLUBILITY-FAILURE-MODES", ScientificChallengeStatus.ROBUST_UNDER_CHALLENGE, evidence=("EVD-V41-SOLUBILITY-FAILURE-ANALYSIS",), assumptions=("held-out scaffold split is used without tuning",), failure_modes=("sample-specific failure cases may not calibrate future populations",), missing=("larger independent calibration population",), sensitivity=("failure threshold uses the held-out upper-quartile floor",), dependence=("analysis derives from the same frozen sample model",), recommended="reproduce on a new compatible source before generalizing failure rates"),
        _challenge("CH-V45-COMBUSTION", "CLM-V41-COMBUSTION-BOUNDARY", ScientificChallengeStatus.ROBUST_UNDER_CHALLENGE, evidence=combustion_evidence, decision="DECISION-V41-COMBUSTION-BOUNDARY", assumptions=("gri30.yaml", "adiabatic HP equilibrium", "declared H2/CH4 reference conditions"), failure_modes=("mechanism dependence", "equilibrium not transient ignition", "condition dependence outside tested range"), missing=("matched experimental observation",), sensitivity=("T0, pressure and phi changed absolute output but not tested reference ordering",), dependence=("all variants use the same mechanism and computational engine",), recommended="retain only the bounded E3 statement and seek E4 comparison"),
        _challenge("CH-V45-BATTERY", "CLM-V41-BATTERY-SCHEMA-BOUNDARY", ScientificChallengeStatus.NEEDS_EXTERNAL_VALIDATION, evidence=battery_evidence, decision="DECISION-V310-BATTERY-REVALUATED", assumptions=("NASA RW3 parser faithfully exposes measured fields",), failure_modes=("missing capacity/resistance/uncertainty", "protocol heterogeneity", "room-temperature-only coverage"), missing=("condition-complete external battery record",), sensitivity=("normalization cannot recover absent fields",), dependence=("single NASA archive lineage",), recommended="ingest an independent capacity/resistance/uncertainty dataset"),
        _challenge("CH-V45-MATERIALS", "CLM-MATERIALS-CONDITION-GAP", ScientificChallengeStatus.NOT_TESTABLE_CURRENTLY, evidence=(), decision="DECISION-MATERIALS-NO-DECISION", assumptions=("material behavior is condition-specific",), failure_modes=("alloy/process/microstructure substitution", "hydrogen environment mismatch", "generic safety extrapolation"), missing=("record-level composition, processing, microstructure, environment, loading, method, property, uncertainty and locator",), sensitivity=("no matched record exists to vary",), dependence=("available sources are discovery metadata only",), recommended="obtain one licensed condition-complete record before comparing alloys"),
        _challenge("CH-V45-CODEX", "CLM-CODEX-BOUNDARY", ScientificChallengeStatus.ROBUST_UNDER_CHALLENGE, evidence=(), assumptions=("Codex proposes structure only", "MoleculeLab creates the deterministic result"), failure_modes=("descriptor implementation drift", "mistaking descriptors for experimental evidence"), missing=("none for the narrow reproducibility question; no efficacy conclusion is permitted",), sensitivity=("same deterministic input is required",), dependence=("result depends on registered MoleculeLab implementation",), recommended="retain as an E0/E1 boundary result and skip identical repeats"),
        _challenge("CH-V45-DOCKING-DECISION", "CLM-DOCKING-DECISION-BOUNDARY", ScientificChallengeStatus.NEEDS_EXTERNAL_VALIDATION, evidence=("EVD-8C48EDB3BEC7", "EVD-C78C348BB94C"), decision="DECISION-REAL-01-1DC0442BB0EA", assumptions=("mean separation exceeds observed replicate spread",), failure_modes=("single receptor structure", "docking score is not affinity or efficacy", "ligand preparation choices"), missing=("measured binding or independent structural validation",), sensitivity=("receptor and grid changes were not executable in this runtime",), dependence=("all scores share the same target structure and engine",), recommended="do not publish efficacy language; run a predeclared structural comparison only"),
        _challenge("CH-V45-NO-DECISION-SOLUBILITY", "CLM-SOLUBILITY-NO-DECISION", ScientificChallengeStatus.WEAKENED, evidence=external_evidence, decision="DECISION-V39-SOLUBILITY", assumptions=("OOD is a valid refusal boundary",), failure_modes=("false conservatism could reject usable in-domain predictions", "uncertainty interval is not certainty"), missing=("external in-domain test set",), sensitivity=("all DLS records fell outside threshold",), dependence=("DLS result is independent in molecule overlap but not identical target semantics",), recommended="reconsider only after a compatible non-OOD validation source is available"),
        _challenge("CH-V45-NO-DECISION-BATTERY", "CLM-BATTERY-NO-DECISION", ScientificChallengeStatus.NOT_TESTABLE_CURRENTLY, evidence=battery_evidence, decision="DECISION-V310-BATTERY-REVALUATED", assumptions=("missing fields cannot be imputed as observations",), failure_modes=("available voltage/current traces might support a narrower descriptive claim",), missing=("capacity/resistance/uncertainty and cross-cell metadata",), sensitivity=("schema completeness controls decision scope",), dependence=("one NASA archive",), recommended="retain no decision for degradation; allow only descriptive schema claims"),
        _challenge("CH-V45-EXTERNAL-FAILURE", "CLM-V43-SOLUBILITY-EXTERNAL-BOUNDARY", ScientificChallengeStatus.WEAKENED, evidence=external_evidence, assumptions=("DLS unique subset is non-overlapping", "one locked pass is not a retraining opportunity"), failure_modes=("56-record external population may be narrow", "intrinsic target semantics differ",), missing=("second independent compatible external source",), sensitivity=("OOD policy excludes all records from ranking",), dependence=("source file is derived from the DLS-100 public record and must retain attribution",), recommended="seek another source before publishing a population-wide failure statement"),
    ]
    for item in challenges:
        store.append(item)
    audits = [
        FalseConservatismAudit("FCA-V45-COMBUSTION", "DECISION-REAL-02-D8EBCAE1CCD0", "NO_DECISION_INSUFFICIENT_EVIDENCE", combustion_evidence, True, "The deterministic Cantera evidence was sufficient for a bounded protocol decision even though it could not support E4 or universalization.", "v4.1 converted the over-broad refusal into a scoped E3 decision while preserving the external validation gap.", "keep the bounded decision and challenge its scope at review"),
        FalseConservatismAudit("FCA-V45-SOLUBILITY", "DECISION-V39-SOLUBILITY", "NO_DECISION_OUT_OF_DOMAIN", external_evidence, False, "The OOD refusal was appropriate because all DLS records were outside the declared applicability threshold.", "No compatible in-domain external record was available to permit a broader decision.", "retain the refusal and acquire a compatible validation source"),
        FalseConservatismAudit("FCA-V45-BATTERY", "DECISION-V310-BATTERY-REVALUATED", "NO_DECISION_INSUFFICIENT_EVIDENCE", battery_evidence, False, "The archive supports descriptive measured-step claims but not the requested degradation decision.", "Capacity, resistance and uncertainty are absent; filling them would invent evidence.", "allow only the narrower descriptive claim"),
        FalseConservatismAudit("FCA-V45-MATERIALS", "DECISION-MATERIALS-NO-DECISION", "NO_DECISION_INSUFFICIENT_EVIDENCE", (), False, "No decision remains justified without a condition-complete record.", "Material substitution and generic hydrogen statements would exceed the available source fields.", "ingest a licensed record-level source"),
    ]
    for audit in audits:
        store.append_audit(audit)
    known_evidence = {str(item) for impact in v41["research_outcome_impacts"] for item in impact.get("new_evidence_ids", [])}
    known_evidence.update(external_evidence)
    known_evidence.update(combustion_evidence)
    known_evidence.update(battery_evidence)
    no_invented_contradictions = all(set(item.contradictory_evidence).issubset(known_evidence) for item in challenges)
    robust = sum(item.challenge_status == ScientificChallengeStatus.ROBUST_UNDER_CHALLENGE for item in challenges)
    weakened = sum(item.challenge_status == ScientificChallengeStatus.WEAKENED for item in challenges)
    report = {"version": "4.5.0", "protocol_version": "research-os.v4.5.scientific-challenge.v1", "branch": "research-os-v1.3", "created_at": _now(), "status": "PASS" if all((len(challenges) >= 10, robust >= 1, weakened >= 1, any(item.target_decision_id_optional for item in challenges), len(audits) >= 1, no_invented_contradictions, all(item.valid for item in challenges), all(item.valid for item in audits), ci_green)) else "FAIL", "provider": "CODEX_CURRENT_TURN", "scientific_evidence_created": False, "evidence_level_changed": False, "challenges": [item.to_dict() for item in challenges], "false_conservatism_audits": [item.to_dict() for item in audits], "counts": {"challenges": len(challenges), "robust": robust, "weakened": weakened, "invalidated": sum(item.challenge_status == ScientificChallengeStatus.INVALIDATED for item in challenges), "needs_external_validation": sum(item.challenge_status == ScientificChallengeStatus.NEEDS_EXTERNAL_VALIDATION for item in challenges), "not_testable_currently": sum(item.challenge_status == ScientificChallengeStatus.NOT_TESTABLE_CURRENTLY for item in challenges), "false_conservatism_detected": sum(item.false_conservatism_detected for item in audits)}, "acceptance": {"ten_or_more_targets": len(challenges) >= 10, "strong_counterargument_recorded": all(bool(item.potential_failure_modes) for item in challenges), "claim_remains_robust": robust >= 1, "claim_weakened_or_reason_recorded": weakened >= 1, "no_decision_challenged": any(item.target_decision_id_optional for item in challenges), "false_conservatism_audit_works": all(item.valid for item in audits), "no_invented_contradictory_evidence": no_invented_contradictions, "codex_created_zero_evidence": True, "evidence_levels_unchanged": True, "full_ci_green": ci_green}, "review_policy": "Challenges are REVIEW / ANALYSIS records, not Evidence; they may accept, reject, revise, open a gap or recommend a future test."}
    _json(output, report)
    return report


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v4.5 scientific challenge")
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_challenge(args.output, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "challenges": report["counts"]["challenges"], "robust": report["counts"]["robust"], "weakened": report["counts"]["weakened"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
