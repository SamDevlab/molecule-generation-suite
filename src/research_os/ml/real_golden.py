"""End-to-end real-data golden run for Research OS v1.6."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any
import uuid

from research_os.bundles import BundleVerificationResult, ResearchBundle, verify_bundle
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.datasets import AQSOLDB_G_SAMPLE_SPEC, RealDatasetIngestResult, ingest_aqsoldb_g
from research_os.environment import EnvironmentManifest, capture_environment
from research_os.knowledge.claims import ClaimStatus, ScientificClaim
from research_os.ledger import LedgerRegistration, RunIndexRecord, RunRegistry
from research_os.ml.promotion import ModelPromotionEngine, PromotionDecision, PromotionPolicy
from research_os.ml.real import RealMLResult, make_real_split, train_real_solubility_model


@dataclass(frozen=True)
class RealGoldenRunResult:
    ingestion: RealDatasetIngestResult
    ml: RealMLResult
    promotion: PromotionDecision
    run: RunManifest
    claim: ScientificClaim
    environment: EnvironmentManifest
    bundle: ResearchBundle
    verification: BundleVerificationResult
    ledger_registration: LedgerRegistration
    ledger_record: RunIndexRecord

    @property
    def passed(self) -> bool:
        return self.verification.passed and self.run.sealed

    def to_dict(self) -> dict[str, Any]:
        return {
            "ingestion": self.ingestion.to_dict(),
            "ml": self.ml.to_dict(),
            "promotion": {"status": self.promotion.status.value, "reason": self.promotion.reason, "evidence": self.promotion.evidence.payload, "gates": [{"rule_id": gate.rule_id, "status": gate.status.value, "reason": gate.reason, "diagnostics": gate.diagnostics} for gate in self.promotion.gates]},
            "run": self.run._serializable(),
            "claim": self.claim.to_dict(),
            "environment": self.environment.to_dict(),
            "bundle": {"bundle_id": self.bundle.bundle_id, "run_id": self.bundle.run_id, "root": self.bundle.root, "bundle_hash": self.bundle.bundle_hash, "sealed": self.bundle.sealed},
            "verification": {"status": self.verification.status.value, "gates": [{"rule_id": gate.rule_id, "status": gate.status.value, "reason": gate.reason} for gate in self.verification.gates]},
            "ledger_registration": {"run_id": self.ledger_registration.run_id, "status": self.ledger_registration.status.value, "bundle_id": self.ledger_registration.bundle_id},
            "ledger_record": self.ledger_record.to_dict(),
        }


def _evidence_id(kind: str) -> str:
    return f"EVD-REAL-{kind.upper()}-{uuid.uuid4().hex[:8].upper()}"


def run_real_data_golden(
    output_root: str | Path,
    *,
    source_path: str | Path | None = None,
    repo_root: str | Path | None = None,
    run_id: str | None = None,
) -> RealGoldenRunResult:
    """Run the checked-in real-data sample through curation, ML and ledger."""

    output = Path(output_root)
    output.mkdir(parents=True, exist_ok=True)
    source = Path(source_path) if source_path is not None else Path(__file__).resolve().parents[3] / "examples" / "real_data" / "aqsoldb_g_sample.csv"
    environment = capture_environment(repo_root=repo_root or Path(__file__).resolve().parents[3])
    ingestion = ingest_aqsoldb_g(source, output / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    data_split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, strategy="scaffold_split", seed=42, split_id="SPLIT-REAL-DATA-GOLDEN")
    ml = train_real_solubility_model(ingestion.records, ingestion.manifest, output / "ml", data_split=data_split, split_manifest=split_manifest, model_id="MODEL-AQSOLDB-G-REAL-GOLDEN", training_run_id="TRN-AQSOLDB-G-REAL-GOLDEN", seed=42, alpha=1.0, external_test_acceptable=False, environment_id=environment.environment_id, git_commit=environment.git.get("commit"))
    promotion = ModelPromotionEngine(policy=PromotionPolicy(require_validation_pass=True, require_external_test=True, require_applicability_domain=True, require_calibration=True, max_ood_score=0.7)).evaluate(ml.model_artifact, ml.champion, validation=ml.validation)
    run = RunManifest(
        lab="ResearchOS-ML",
        experiment="real_data_validation_aqsoldb_g",
        run_id=run_id or "REAL-DATA-GOLDEN-RUN",
        inputs={"dataset_id": ingestion.manifest.dataset_id, "dataset_version": ingestion.manifest.version, "source_id": ingestion.source.source_id, "target": ingestion.manifest.target, "units": ingestion.manifest.units},
        config={"split_strategy": ml.split.strategy.value, "split_manifest_hash": ml.split.manifest_hash, "model_id": ml.model_artifact.model_id, "training_run_id": ml.training_run.training_run_id, "champion_model_id": ml.champion.model_id, "promotion_policy": {"require_external_test": True, "require_applicability_domain": True, "require_calibration": True, "max_ood_score": 0.7}},
    )
    run.start()
    run.attach_dataset(ingestion.manifest)
    run.attach_environment(environment)
    provenance = ProvenanceRecord(source_type=SourceType.DATASET, source_id=ingestion.source.source_id, title=ingestion.source.title, citation=ingestion.source.citation, doi="10.1038/s41597-019-0151-1", url=ingestion.source.url, license=ingestion.source.license, method=ingestion.manifest.measurement_method, conditions=ingestion.manifest.conditions, notes=ingestion.source.notes)
    run.provenance.append(provenance)
    data_evidence = Evidence(_evidence_id("DATA"), "real_dataset_source_validation", EvidenceLevel.E4_CURATED_EXPERIMENTAL, ingestion.source.url, {"source_record": ingestion.source.to_dict(), "validation": ingestion.validation.to_dict(), "dataset_manifest": ingestion.manifest.to_dict(), "raw_sha256": ingestion.source.source_sha256}, (provenance.provenance_id,))
    ml_evidence = Evidence(_evidence_id("ML"), "real_model_training_validation", EvidenceLevel.E1_ML, "Research OS NumPy ridge baseline", {"model_id": ml.model_artifact.model_id, "training_run_id": ml.training_run.training_run_id, "dataset_id": ml.dataset.dataset_id, "feature_schema_id": ml.feature_schema.feature_schema_id, "training_run": ml.training_run.to_dict(), "split_manifest": ml.split.to_dict(), "validation": ml.validation.to_dict()}, (provenance.provenance_id,))
    ad_evidence = Evidence(_evidence_id("AD"), "applicability_domain_and_uncertainty", EvidenceLevel.E1_ML, "Morgan/Tanimoto AD and residual interval", {"model_id": ml.model_artifact.model_id, "training_run_id": ml.training_run.training_run_id, "applicability_domain": ml.validation.applicability_domain.to_dict() if ml.validation.applicability_domain else None, "predictions": [item.to_dict() for item in ml.test_predictions], "calibration": ml.validation.calibration}, (provenance.provenance_id,))
    promotion_evidence = promotion.evidence
    run.evidence.extend((data_evidence, ml_evidence, ad_evidence, promotion_evidence))
    run.gates.append(GateResult("GATE-REAL-DATA", ingestion.validation.rule_id, ingestion.validation.status, "real source validated and recorded", evidence_ids=(data_evidence.evidence_id,), diagnostics={"row_count": ingestion.validation.row_count, "raw_sha256": ingestion.source.source_sha256}))
    run.gates.append(GateResult("GATE-REAL-ML", "ML-METRICS-001", GateStatus.PASS if ml.validation.passed else GateStatus.FAIL, "MAE, RMSE and R2 recorded on the scaffold-held-out split", evidence_ids=(ml_evidence.evidence_id,), diagnostics=ml.validation.metrics))
    for gate in promotion.gates:
        run.gates.append(GateResult(f"GATE-PROMOTION-{gate.rule_id}", gate.rule_id, gate.status, gate.reason, evidence_ids=(promotion_evidence.evidence_id,), diagnostics=gate.diagnostics))
    claim = ScientificClaim(
        statement="The AqSolDB-G real-data sample was ingested, scaffold-split, modeled with a Morgan/ridge baseline, assessed for applicability domain and uncertainty, and subjected to an explicit promotion decision.",
        run_id=run.run_id,
        evidence_ids=tuple(evidence.evidence_id for evidence in run.evidence),
        minimum_evidence_level=EvidenceLevel.E1_ML,
        status=ClaimStatus.SUPPORTED if promotion.status.value == "PROMOTED" else ClaimStatus.INSUFFICIENT_EVIDENCE,
        limitations=("The checked-in sample is a 46-row subset of AqSolDB-G, not the full release.", "The held-out scaffold split is not an independent external source.", "A rejected promotion decision is not evidence of deployment readiness."),
        conditions={"dataset": ingestion.manifest.dataset_id, "dataset_version": ingestion.manifest.version, "split": ml.split.strategy.value, "target": ingestion.manifest.target, "units": ingestion.manifest.units},
    )
    run.add_claim(claim)
    run.seal()
    bundle = ResearchBundle.create(run, output / "runs", environment=environment, dataset_manifests=(ingestion.manifest,), claims=(claim,), artifacts={"model.json": ml.model_artifact.model_file or "", "model-manifest.json": output / "ml" / "models" / f"{ml.model_artifact.model_id}.manifest.json", "champion.json": ml.champion.model_file or "", "champion-manifest.json": output / "ml" / "models" / f"{ml.champion.model_id}.manifest.json", "split-manifest.json": output / "ml" / "models" / "split-manifest.json"}, pack_artifacts=True)
    verification = verify_bundle(bundle.root)
    with RunRegistry(output / "ledger") as ledger:
        registration = ledger.register_run(bundle, model_ids=(ml.model_artifact.model_id,), tags=("v1.6", "real-data", "aqsoldb"))
        ledger_record = ledger.get_run(run.run_id)
    return RealGoldenRunResult(ingestion, ml, promotion, run, claim, environment, bundle, verification, registration, ledger_record)
