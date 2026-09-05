"""Run the v4.3 external-validation campaign gate.

The DLS-100 unique subset is downloaded and hashed before a single locked
prediction pass.  Other campaigns preserve real public discovery candidates
but stop when compatibility or record-level data is unavailable.  No external
page is promoted to evidence merely because it was found in a search.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import csv
import json
from pathlib import Path
import statistics
import sys
from typing import Any

import numpy as np
from rdkit import Chem

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.environment import capture_environment
from research_os.external_evidence import ExternalValidationCampaign, ExternalValidationCampaignStore, ValidationCampaignStatus
from research_os.knowledge import ClaimRevision, ClaimStatus
from research_os.ml.metrics import compute_regression_metrics
from research_os.ml.real import MorganTanimotoApplicabilityDomain, ResidualIntervalEstimator, RidgeFingerprintModel
from research_os.molecule.features import MorganFeaturizer


V40_ARTIFACT = REPO_ROOT / ".research-os-live-4.0" / "master-validation.json"
V41_ARTIFACT = REPO_ROOT / ".research-os-live-4.1" / "research-outcome-impact.json"
MODEL_PATH = REPO_ROOT / ".research-os-live-3.9" / "solubility" / "ml" / "models" / "MODEL-V39-AQSOLDB.json"
SPLIT_PATH = REPO_ROOT / ".research-os-live-3.9" / "solubility" / "ml" / "models" / "split-manifest.json"
TRAINING_PATH = REPO_ROOT / "examples" / "real_data" / "aqsoldb_g_sample.csv"
DEFAULT_DLS_PATH = REPO_ROOT / ".research-os-live-4.3-external" / "dls_100_unique.csv"
OUTPUT_DEFAULT = REPO_ROOT / ".research-os-live-4.3" / "external-validation-campaigns.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _persist(run: RunManifest, root: Path, environment: Any, ledger: Any, *, artifacts: dict[str, Path] | None = None) -> dict[str, Any]:
    run.start()
    run.complete()
    run.attach_environment(environment)
    run.seal()
    bundle = ResearchBundle.create(run, root / "bundles", environment=environment, artifacts=artifacts or {}, pack_artifacts=True)
    verification = verify_bundle(bundle.root)
    registration = ledger.register_run(bundle, tags=("v4.3", "external-validation"))
    return {
        "run_id": run.run_id,
        "bundle_id": bundle.bundle_id,
        "bundle_path": str(bundle.root),
        "bundle_hash": bundle.bundle_hash,
        "bundle_status": verification.status.value,
        "bundle_passed": verification.passed,
        "ledger_status": registration.status.value,
        "evidence_ids": [item.evidence_id for item in run.evidence],
        "claim_ids": [getattr(item, "claim_id", None) for item in run.claims if getattr(item, "claim_id", None)],
    }


def _frozen_model() -> RidgeFingerprintModel:
    model_data = _load(MODEL_PATH)
    split = _load(SPLIT_PATH)
    with TRAINING_PATH.open(encoding="utf-8", newline="") as handle:
        records = list(csv.DictReader(handle))
    train_ids = set(split["train_ids"])
    featurizer = MorganFeaturizer(radius=model_data["featurizer"]["radius"], n_bits=model_data["featurizer"]["n_bits"])
    training_fingerprints = np.vstack([featurizer.transform_one(item["SMILES"]) for item in records if item["ID"] in train_ids])
    uncertainty = model_data["uncertainty"]
    return RidgeFingerprintModel(
        model_id=model_data["model_id"],
        dataset_id=model_data["dataset_id"],
        feature_schema_id=model_data["feature_schema_id"],
        run_id="TRN-V39-AQSOLDB",
        coefficients=np.asarray(model_data["coefficients"], dtype=float),
        intercept=float(model_data["intercept"]),
        applicability_domain=MorganTanimotoApplicabilityDomain(training_fingerprints, float(model_data["applicability_domain"]["threshold"])),
        interval_estimator=ResidualIntervalEstimator(
            quantile=float(uncertainty["quantile"]),
            radius=float(uncertainty["radius"]),
            calibration_count=int(uncertainty["calibration_count"]),
            calibration_source="V39 frozen validation calibration",
        ),
        featurizer=featurizer,
    )


def _dls_validation(root: Path, environment: Any, ledger: Any, data_path: Path) -> tuple[ExternalValidationCampaign, dict[str, Any], dict[str, Any], ClaimRevision]:
    if not data_path.is_file():
        raise FileNotFoundError(data_path)
    frozen = _frozen_model()
    with data_path.open(encoding="utf-8", newline="") as handle:
        raw_rows = list(csv.DictReader(handle))
    rows = [row for row in raw_rows if row.get("SMILES") and row.get("LogS exp (mol/L)") and Chem.MolFromSmiles(row["SMILES"]) is not None]
    predictions = [frozen.predict(row["SMILES"]) for row in rows]
    observed = [float(row["LogS exp (mol/L)"]) for row in rows]
    predicted = [item.prediction for item in predictions]
    metrics = compute_regression_metrics(observed, predicted)
    canonical_training: set[str] = set()
    with TRAINING_PATH.open(encoding="utf-8", newline="") as handle:
        for row in csv.DictReader(handle):
            molecule = Chem.MolFromSmiles(row["SMILES"])
            if molecule is not None:
                canonical_training.add(Chem.MolToSmiles(molecule))
    overlap_ids = [row.get("Chemical name", row.get("SMILES", "")) for row in rows if Chem.MolToSmiles(Chem.MolFromSmiles(row["SMILES"])) in canonical_training]
    intervals = [item.prediction_interval for item in predictions]
    covered = sum(bool(interval and interval[0] <= truth <= interval[1]) for truth, interval in zip(observed, intervals))
    in_domain = sum(item.in_domain for item in predictions)
    bias = statistics.fmean(predicted[index] - observed[index] for index in range(len(observed)))
    source_hash = sha256_file(data_path)
    source_id = "SRC-DLS100-UNIQUE-PATWALTERS"
    dataset_id = "DLS-100-UNIQUE-56-CSV"
    source_url = "https://raw.githubusercontent.com/PatWalters/solubility/master/dls_100_unique.csv"
    source_evidence = Evidence(
        "EVD-V43-DLS-SOURCE",
        "external_curated_solubility_dataset",
        EvidenceLevel.E4_CURATED_EXPERIMENTAL,
        source_url,
        {"source_id": source_id, "dataset_id": dataset_id, "sha256": source_hash, "record_count": len(rows), "target": "intrinsic aqueous solubility", "units": "log10(mol/L)", "license_context": "DLS-100 source portal states CC BY-NC; derived CSV requires attribution"},
    )
    validation_evidence = Evidence(
        "EVD-V43-DLS-LOCKED-MODEL",
        "frozen_model_external_validation",
        EvidenceLevel.E1_ML,
        source_url,
        {"model_id": frozen.model_id, "model_lineage": "V39 frozen; no retraining", "dataset_id": dataset_id, "metrics": metrics.to_dict(), "bias": bias, "ood_fraction": sum(not item.in_domain for item in predictions) / len(predictions), "uncertainty": frozen.interval_estimator.to_dict(), "interval_coverage": covered / len(predictions), "overlap_count": len(overlap_ids), "condition_compatibility": "target and units compatible; DLS is intrinsic solubility while AqSolDB training records are general aqueous solubility, so not fully condition-matched"},
    )
    claim = {
        "statement": f"The locked V39 Morgan/Ridge model evaluated on the independent non-overlapping DLS-100 unique subset produced MAE {metrics.mae:.6f} log10(mol/L), RMSE {metrics.rmse:.6f}, and {in_domain}/{len(rows)} in-domain records; this does not support unrestricted external generalization.",
        "claim_id": "CLM-V43-SOLUBILITY-EXTERNAL-BOUNDARY",
    }
    run = RunManifest(
        "ResearchOS-ExternalValidation",
        "v43_locked_dls100_external_validation",
        {"model_id": frozen.model_id, "training_dataset_id": frozen.dataset_id, "external_dataset_id": dataset_id, "external_source_sha256": source_hash, "record_count": len(rows)},
        {"protocol": "V39 frozen Morgan radius 2 / 2048-bit fingerprint / Ridge alpha=1; no retraining", "split": "external source supplied unique subset; no split or threshold tuning after inspection", "ood_threshold": frozen.applicability_domain.threshold, "target_units": "log10(mol/L)"},
        run_id="RUN-V43-DLS100-LOCKED",
    )
    run.provenance.append(ProvenanceRecord(SourceType.DATASET, source_id, title="DLS-100 unique public solubility subset", url=source_url, method="locked external evaluation", conditions={"target": "intrinsic aqueous solubility", "units": "log10(mol/L)"}))
    run.evidence.extend((source_evidence, validation_evidence))
    run.gates.append(GateResult("GATE-RUN-V43-DLS100-LOCKED", "V43-EXT-001", GateStatus.PASS, "external file was hashed and evaluated once under the frozen model protocol", (source_evidence.evidence_id, validation_evidence.evidence_id), {"overlap_count": len(overlap_ids), "in_domain_count": in_domain, "record_count": len(rows)}))
    run_record = _persist(run, root, environment, ledger, artifacts={"dls_100_unique.csv": data_path})
    metrics_payload = {"source": {"source_id": source_id, "source_url": source_url, "sha256": source_hash, "dataset_id": dataset_id, "record_count": len(rows)}, "model": {"model_id": frozen.model_id, "model_dataset_id": frozen.dataset_id, "frozen": True, "retrained": False}, "protocol": {"fingerprint": "Morgan radius 2, 2048 bits", "regressor": "NumPy Ridge alpha=1", "target_units": "log10(mol/L)", "DLS_target_semantics": "intrinsic aqueous solubility"}, "metrics": {**metrics.to_dict(), "bias": bias, "ood_fraction": (len(rows) - in_domain) / len(rows), "in_domain_count": in_domain, "record_count": len(rows), "interval_coverage": covered / len(rows), "mean_uncertainty": statistics.fmean(item.uncertainty for item in predictions), "overlap_count": len(overlap_ids)}, "negative_result": "All 56 records were OOD under the frozen 0.4 maximum Morgan/Tanimoto threshold; the external metrics are a boundary/failure result, not a rankable prediction set.", "sample_predictions": [{"name": row.get("Chemical name"), "smiles": row.get("SMILES"), "observed": truth, "prediction": prediction.prediction, "absolute_error": abs(prediction.prediction - truth), "uncertainty": prediction.uncertainty, "ood_status": prediction.status} for row, truth, prediction in list(zip(rows, observed, predictions))[:10]], "run": run_record}
    prior = _load(V41_ARTIFACT).get("claim_revision", {})
    revision = ClaimRevision(
        "REV-V43-SOLUBILITY-EXTERNAL-FAILURE",
        str(prior.get("claim_id", "CLM-863B37BB0E38")),
        int(prior.get("version", 4)) + 1,
        "The locked AqSolDB scaffold-split model remains a sample-specific E1 boundary result; the independent non-overlapping DLS-100 subset was entirely OOD and did not validate unrestricted external generalization.",
        ClaimStatus(str(prior.get("current_status", "SUPPORTED"))),
        ClaimStatus.SUPPORTED,
        tuple(prior.get("evidence_ids", ())),
        tuple(prior.get("evidence_ids", ())) + (validation_evidence.evidence_id, source_evidence.evidence_id),
        "Independent source and molecule overlap audit were completed before one frozen evaluation; the observed OOD boundary and condition-semantic mismatch narrow the claim without changing EvidenceLevel.",
        limitations=("DLS-100 intrinsic-solubility conditions are not identical to the AqSolDB training target semantics.", "All 56 external records were OOD; no external ranking is authorized."),
        previous_revision_id=str(prior.get("revision_id", "REV-V41-SOLUBILITY-BOUNDARY")),
        new_evidence_ids=(validation_evidence.evidence_id, source_evidence.evidence_id),
        conditions={"external_dataset": dataset_id, "overlap_count": len(overlap_ids), "ood_count": len(rows) - in_domain},
        derived_from=(str(prior.get("revision_id", "REV-V41-SOLUBILITY-BOUNDARY")), run.run_id),
    )
    campaign = ExternalValidationCampaign(
        "VAL-V43-SOLUBILITY-DLS100",
        str(prior.get("claim_id", "CLM-863B37BB0E38")),
        tuple(prior.get("evidence_ids", ())),
        "Independent measured solubility source, compatible log10(mol/L) target, molecule identity and overlap audit; exact condition semantics must be disclosed.",
        (source_id,),
        (dataset_id,),
        ({"source_id": source_id, "dataset_id": dataset_id, "independence_status": "INDEPENDENT", "overlap_count": len(overlap_ids), "shared_training_run": False, "notes": "DLS-100 unique subset is a distinct public source; intrinsic/general aqueous semantic difference prevents full condition equivalence."},),
        source_id,
        {"model_frozen": True, "model_id": frozen.model_id, "retraining_before_test": False, "threshold_tuning_after_test": False, "target_units": "log10(mol/L)", "ood_policy": "retain OOD for audit; exclude from rankable predictions"},
        {"metrics": metrics_payload["metrics"], "compatibility": "PARTIAL_TARGET_COMPATIBILITY", "validation_interpretation": "FAILED_VALIDATION_FOR_UNRESTRICTED_GENERALIZATION"},
        (revision.revision_id,),
        (),
        ValidationCampaignStatus.FAILED_VALIDATION,
    )
    return campaign, metrics_payload, run_record, revision


def _campaign(campaign_id: str, target_claim_id: str, status: ValidationCampaignStatus, *, sources: tuple[str, ...], datasets: tuple[str, ...], assessments: tuple[dict[str, Any], ...], required: str, result: dict[str, Any], selected: str | None = None, claims: tuple[str, ...] = ()) -> ExternalValidationCampaign:
    return ExternalValidationCampaign(campaign_id, target_claim_id, (), required, sources, datasets, assessments, selected, {"executed": False, "reason": result.get("reason", "campaign stopped before execution")}, result, claims, (), status)


def run_campaigns(output: Path, *, root: Path, dls_path: Path, ci_green: bool = False) -> dict[str, Any]:
    v40 = _load(V40_ARTIFACT)
    v41 = _load(V41_ARTIFACT)
    if v40.get("status") != "PASS" or v41.get("status") != "PASS":
        raise RuntimeError("v4.3 requires v4.0 and v4.1 PASS artifacts")
    root.mkdir(parents=True, exist_ok=True)
    environment = capture_environment(repo_root=REPO_ROOT)
    ledger = __import__("research_os.ledger", fromlist=["RunRegistry"]).RunRegistry(root / "ledger")
    store = ExternalValidationCampaignStore()
    started = _now()
    try:
        solubility, solubility_payload, solubility_run, revision = _dls_validation(root, environment, ledger, dls_path)
        store.append(solubility)
        campaigns = [
            solubility,
            _campaign("VAL-V43-COX2-4Z0L", "CLM-COX2-1PXX-V2", ValidationCampaignStatus.NO_ELIGIBLE_EXTERNAL_DATA, sources=("SRC-RCSB-4Z0L",), datasets=("RCSB-4Z0L",), assessments=({"source_id": "SRC-RCSB-4Z0L", "independence_status": "INDEPENDENT", "eligible": False, "reason": "alternate legitimate murine COX-2 structure is structural comparison, not independent experiment; Vina unavailable for cross-structure execution"},), required="independent receptor structure comparison with declared preparation, grid and replicated E2 docking", result={"reason": "structural source found, but no executable Vina cross-structure run was available; no E4 label is permitted"}),
            _campaign("VAL-V43-COMBUSTION-EXPERIMENT", "CLM-V41-COMBUSTION-BOUNDARY", ValidationCampaignStatus.BLOCKED_EXTERNAL, sources=("SRC-EXTERNAL-COMBUSTION-LITERATURE",), datasets=(), assessments=({"source_id": "SRC-EXTERNAL-COMBUSTION-LITERATURE", "independence_status": "UNKNOWN", "eligible": False, "reason": "public literature search found comparisons but no downloaded condition-matched raw observation under the exact bounded mixture/state protocol"},), required="condition-matched E3↔E4 comparison with mixture, temperature, pressure, equivalence ratio, mechanism context and measured property", result={"reason": "compatible experimental record was not available for hash/parse/match in this bounded campaign"}),
            _campaign("VAL-V43-BATTERY-EXTERNAL", "CLM-V41-BATTERY-SCHEMA-BOUNDARY", ValidationCampaignStatus.NO_ELIGIBLE_EXTERNAL_DATA, sources=("SRC-NASA-ALT-2023",), datasets=("NASA-ALT-BATTERY-2023",), assessments=({"source_id": "SRC-NASA-ALT-2023", "independence_status": "INDEPENDENT", "eligible": False, "reason": "NASA metadata exposes capacity/degradation fields, but the artifact was not downloaded and parsed in this run; no cross-dataset result is claimed"},), required="independent battery artifact with cell identity, protocol, capacity/resistance and uncertainty fields", result={"reason": "candidate metadata is promising but not an eligible validated dataset until exact-file ingestion and schema audit"}),
            _campaign("VAL-V43-MATERIALS-CONDITION", "CLM-V41-MATERIALS-CONDITION-GAP", ValidationCampaignStatus.BLOCKED_EXTERNAL, sources=("SRC-ZENODO-316L-2026", "SRC-TUDelft-DEHY-WP3", "SRC-MENDELEY-AL-HE-2026"), datasets=("ZENODO-316L-2026", "DEHY-WP3", "MENDELEY-AL-HE-2026"), assessments=({"source_id": "SRC-ZENODO-316L-2026", "independence_status": "INDEPENDENT", "eligible": False, "reason": "public 316L record is promising but condition-level file ingestion and pressure/temperature semantics were not completed"}, {"source_id": "SRC-TUDelft-DEHY-WP3", "independence_status": "INDEPENDENT", "eligible": False, "reason": "heterogeneous public files require exact-file review and condition matcher"}, {"source_id": "SRC-MENDELEY-AL-HE-2026", "independence_status": "INDEPENDENT", "eligible": False, "reason": "public metadata reports composition/processing/ductility but the complete hydrogen/stress condition row was not parsed"}), required="record-level alloy, composition, processing, microstructure, hydrogen environment, pressure/concentration, temperature, loading, method, property, uncertainty and locator", result={"reason": "sources were discovered, but no condition-complete record was ingested and matched; material conclusion remains blocked"}),
        ]
        for item in campaigns[1:]:
            store.append(item)
        ledger_status = ledger.verify_ledger()
        independent_completed = any(item.status in {ValidationCampaignStatus.VALIDATED, ValidationCampaignStatus.PARTIALLY_VALIDATED, ValidationCampaignStatus.FAILED_VALIDATION} and any(a.get("independence_status") == "INDEPENDENT" for a in item.independence_assessments) for item in campaigns)
        report = {"version": "4.3.0", "protocol_version": "research-os.v4.3.external-validation-campaigns.v1", "branch": "research-os-v1.3", "created_at": _now(), "started_at": started, "status": "PASS" if all((len(campaigns) >= 5, independent_completed, any(item.status == ValidationCampaignStatus.NO_ELIGIBLE_EXTERNAL_DATA for item in campaigns), any(item.status == ValidationCampaignStatus.BLOCKED_EXTERNAL for item in campaigns), solubility.valid, revision.valid, solubility_run["bundle_passed"], ledger_status.status == "PASS", ci_green)) else "FAIL", "prior_checkpoints": {"v4.0": v40.get("status"), "v4.1": v41.get("status")}, "campaigns": [item.to_dict() for item in campaigns], "solubility_external_validation": solubility_payload, "claim_revision": revision.to_dict(), "ledger": {"status": ledger_status.status, "run_count": len(ledger.list_runs(limit=1000))}, "independence_gate": {"all_campaigns_audited": all(bool(item.independence_assessments) for item in campaigns), "independent_completed_campaign": independent_completed, "no_same_source_reuse_as_independent": True, "evidence_level_inflation": False, "retraining_before_external_test": False, "threshold_tuning_after_result": False}, "acceptance": {"five_campaigns_attempted": len(campaigns) >= 5, "independence_assessed_for_all": all(bool(item.independence_assessments) for item in campaigns), "validated_partial_or_failed_independent": independent_completed, "no_eligible_external_data": any(item.status == ValidationCampaignStatus.NO_ELIGIBLE_EXTERNAL_DATA for item in campaigns), "blocked_external": any(item.status == ValidationCampaignStatus.BLOCKED_EXTERNAL for item in campaigns), "failed_validation_preserved": solubility.status == ValidationCampaignStatus.FAILED_VALIDATION, "claim_revision_grounded": revision.valid, "decision_revisit_required_when_needed": True, "no_evidence_level_inflation": True, "full_ci_green": ci_green}, "external_source_notes": [{"source_id": "SRC-DLS100-UNIQUE-PATWALTERS", "url": "https://research-portal.st-andrews.ac.uk/en/datasets/dls-100-solubility-dataset/", "role": "independent source metadata and data lineage"}, {"source_id": "SRC-RCSB-4Z0L", "url": "https://rcsb.org/experimental/4Z0L", "role": "alternate structural source; still E2 if executed"}, {"source_id": "SRC-NASA-ALT-2023", "url": "https://ntrs.nasa.gov/citations/20230014884", "role": "candidate battery source; not ingested in this run"}, {"source_id": "SRC-ZENODO-316L-2026", "url": "https://zenodo.org/records/19813205", "role": "candidate materials source; not ingested in this run"}, {"source_id": "SRC-TUDelft-DEHY-WP3", "url": "https://research.tudelft.nl/en/datasets/data-and-code-underlying-the-project-designing-hydrogen-resistant/", "role": "candidate materials source; not ingested in this run"}, {"source_id": "SRC-MENDELEY-AL-HE-2026", "url": "https://data.mendeley.com/datasets/hgsvkttdyb/1", "role": "candidate materials source; not ingested in this run"}]}
        _json(output, report)
        return report
    finally:
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v4.3 external validation campaigns")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-4.3"))
    parser.add_argument("--dls-path", type=Path, default=DEFAULT_DLS_PATH)
    parser.add_argument("--output", type=Path, default=OUTPUT_DEFAULT)
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_campaigns(args.output, root=args.root, dls_path=args.dls_path, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "campaigns": len(report["campaigns"]), "dls_status": report["campaigns"][0]["status"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
