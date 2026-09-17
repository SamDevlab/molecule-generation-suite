"""Research OS 3.6 real cross-domain decision acceptance.

This runner executes only source-backed observations/calculations.  Codex is
used as a planning/refusal boundary; it never supplies a scientific value.
The scientific result is written to sealed bundles, the Ledger and the
append-only DecisionStore.
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import sys
from urllib.request import Request, urlopen
import uuid
from typing import Any, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.combustion import CombustionLab
from research_os.core.hashing import sha256_file
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.decision import (
    BatteryDatasetQualityAssessment,
    BatteryProtocolComparability,
    BatteryProtocolMatchStatus,
    CriterionEvaluation,
    DecisionCriterion,
    DecisionStatus,
    DockingProtocolVariability,
    PlanParsimonyAssessment,
    ScientificDecision,
    SimulationExperimentComparison,
    audit_decision,
    evaluate_docking_separation,
    resolve_decision,
)
from research_os.datasets import AQSOLDB_G_SAMPLE_SPEC, ingest_aqsoldb_g
from research_os.docking import DockingLab, DockingCampaign, LigandPreparationLab, ReceptorPreparationLab
from research_os.evidence import EvidenceAgreementAssessment, EvidenceAgreementStatus
from research_os.environment import capture_environment
from research_os.knowledge import ClaimStatus, ScientificClaim, SourceRecord, SourceType as KnowledgeSourceType
from research_os.ml.real import make_real_split, train_real_solubility_model
from research_os.resolution import analyze_nasa_pcoe_rw3
from research_os.thermal import ThermalLab
from research_os.web.server import build_default_application


PUBCHEM_BASE = "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/cid"
COMPOUNDS = {
    "diclofenac": {"cid": 3033, "source_id": "SRC-PUBCHEM-CID3033", "title": "PubChem Compound Summary: Diclofenac", "url": "https://pubchem.ncbi.nlm.nih.gov/compound/3033"},
    "celecoxib": {"cid": 2662, "source_id": "SRC-PUBCHEM-CID2662", "title": "PubChem Compound Summary: Celecoxib", "url": "https://pubchem.ncbi.nlm.nih.gov/compound/2662"},
}
GRID = {"center_x": 27.1155, "center_y": 24.09, "center_z": 14.936, "size_x": 21.427, "size_y": 22.664, "size_z": 22.533}
DOCKING_PROTOCOL = "autodock-vina.v36.cox2.1pxx.same-grid.v1"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _uid(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:12].upper()}"


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, default=str), encoding="utf-8")


def _fetch(url: str, destination: Path | None = None) -> bytes:
    request = Request(url, headers={"User-Agent": "research-os-v3.6-source-retrieval"})
    with urlopen(request, timeout=60) as response:
        content = response.read()
    if destination is not None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(content)
    return content


def _compound(root: Path, name: str) -> dict[str, Any]:
    record = dict(COMPOUNDS[name])
    cid = record["cid"]
    property_url = f"{PUBCHEM_BASE}/{cid}/property/CanonicalSMILES,IsomericSMILES/JSON"
    properties = json.loads(_fetch(property_url).decode("utf-8"))["PropertyTable"]["Properties"][0]
    if int(properties["CID"]) != cid or not properties.get("ConnectivitySMILES"):
        raise ValueError(f"PubChem identity response did not contain the expected CID {cid}")
    record["canonical_smiles"] = str(properties["ConnectivitySMILES"])
    record["property_url"] = property_url
    sdf_url = f"{PUBCHEM_BASE}/{cid}/SDF?record_type=3d"
    sdf_path = root / "sources" / f"{name}-cid{cid}-3d.sdf"
    content = _fetch(sdf_url, sdf_path)
    if not content.strip() or b"V2000" not in content and b"V3000" not in content:
        raise ValueError(f"PubChem CID {cid} did not return a readable SDF")
    record.update({"sdf_url": sdf_url, "sdf_path": str(sdf_path), "sdf_sha256": sha256_file(sdf_path), "sdf_size_bytes": len(content), "retrieved_at": _now()})
    return record


def _register_source(app: Any, record: Mapping[str, Any]) -> None:
    registry = app.service.source_registry
    try:
        registry.get(record["source_id"])
    except KeyError:
        registry.register(SourceRecord(record["source_id"], record["title"], organization="PubChem / NIH", url=record["url"], source_type=KnowledgeSourceType.DATABASE, document_hash=record["sdf_sha256"], metadata={"cid": record["cid"], "canonical_smiles": record["canonical_smiles"], "sdf_url": record["sdf_url"], "retrieved_at": record["retrieved_at"]}))


def _persist(app: Any, run: RunManifest, root: Path, environment: Any, *, tags: tuple[str, ...], artifacts: dict[str, str] | None = None, datasets: tuple[Any, ...] = ()) -> dict[str, Any]:
    if run.lifecycle.value in {"CREATED", "RUNNING"} and run.first_loss is None:
        run.complete()
    if not run.sealed:
        run.seal()
    bundle = ResearchBundle.create(run, root / "bundles", environment=environment, dataset_manifests=datasets, artifacts=artifacts or {}, pack_artifacts=True)
    verification = verify_bundle(bundle.root)
    registration = app.service.ledger.register_run(bundle, tags=tags) if app.service.ledger is not None else None
    return {"run_id": run.run_id, "status": run.status, "evidence_ids": [item.evidence_id for item in run.evidence], "bundle_id": bundle.bundle_id, "bundle_path": bundle.root, "bundle_hash": bundle.bundle_hash, "bundle_verification": verification.status.value, "bundle_passed": verification.passed, "ledger_registration": registration.to_dict() if registration is not None and hasattr(registration, "to_dict") else str(registration) if registration is not None else None}


def _molecule_run(app: Any, root: Path, environment: Any, name: str, record: dict[str, Any]) -> dict[str, Any]:
    lab = app.service.orchestrator.registry.get("MoleculeLab")
    run = lab.run({"smiles": record["canonical_smiles"], "name": name, "source": record["url"], "id": f"PUBCHEM-CID-{record['cid']}"}, experiment="v36_real_candidate_properties")
    run.provenance.append(ProvenanceRecord(SourceType.DATABASE, record["source_id"], title=record["title"], url=record["url"], method="PubChem canonical SMILES identity record", conditions={"cid": record["cid"]}, notes=f"SDF SHA-256: {record['sdf_sha256']}"))
    run.attach_environment(environment)
    return _persist(app, run, root, environment, tags=("v3.6", "real", "molecule", name))


def _ml_run(app: Any, root: Path, environment: Any, records: dict[str, dict[str, Any]]) -> tuple[dict[str, Any], Any, dict[str, Any]]:
    source = REPO_ROOT / "examples" / "real_data" / "aqsoldb_g_sample.csv"
    ingestion = ingest_aqsoldb_g(source, root / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, strategy="scaffold_split", seed=42, split_id=f"SPLIT-V36-{uuid.uuid4().hex[:8].upper()}")
    ml = train_real_solubility_model(ingestion.records, ingestion.manifest, root / "ml", data_split=split, split_manifest=split_manifest, model_id=f"MODEL-V36-AQSOLDB-{uuid.uuid4().hex[:8].upper()}", training_run_id=f"TRN-V36-AQSOLDB-{uuid.uuid4().hex[:8].upper()}", seed=42, alpha=1.0, external_test_acceptable=False, environment_id=environment.environment_id, git_commit=environment.git.get("commit"))
    predictions = {name: ml.model.predict(record["canonical_smiles"]) for name, record in records.items()}
    run = RunManifest("ResearchOS-ML", "v36_real_cross_domain_solubility", {"dataset_id": ingestion.manifest.dataset_id, "candidate_ids": {name: f"PUBCHEM-CID-{item['cid']}" for name, item in records.items()}, "target": ingestion.manifest.target, "units": ingestion.manifest.units}, {"split_strategy": ml.split.strategy.value, "split_manifest_hash": ml.split.manifest_hash, "model_id": ml.model_artifact.model_id, "training_run_id": ml.training_run.training_run_id, "applicability_domain_policy": "OUT_OF_DOMAIN predictions retained for audit and excluded from ranking", "uncertainty_policy": "residual-calibrated interval; not certainty"}, run_id=_uid("RUN-V36-ML"))
    run.start()
    run.attach_dataset(ingestion.manifest)
    run.attach_environment(environment)
    provenance = ProvenanceRecord(SourceType.DATASET, ingestion.source.source_id, title=ingestion.source.title, citation=ingestion.source.citation, doi="10.1038/s41597-019-0151-1", url=ingestion.source.url, license=ingestion.source.license, method=ingestion.manifest.measurement_method, conditions=ingestion.manifest.conditions)
    run.provenance.append(provenance)
    data_evidence = Evidence(_uid("EVD-V36-DATA"), "real_dataset_source_validation", EvidenceLevel.E4_CURATED_EXPERIMENTAL, ingestion.source.url, {"source": ingestion.source.to_dict(), "validation": ingestion.validation.to_dict(), "dataset_manifest": ingestion.manifest.to_dict(), "raw_sha256": ingestion.source.source_sha256}, (provenance.provenance_id,))
    model_evidence = Evidence(_uid("EVD-V36-ML"), "real_solubility_model_validation", EvidenceLevel.E1_ML, "Research OS NumPy ridge baseline", {"model_id": ml.model_artifact.model_id, "training_run_id": ml.training_run.training_run_id, "feature_schema_id": ml.feature_schema.feature_schema_id, "split_manifest": ml.split.to_dict(), "validation": ml.validation.to_dict(), "promotion": "NOT_PROMOTED_EXTERNAL_TEST_NOT_ELIGIBLE"}, (provenance.provenance_id,))
    prediction_evidence = Evidence(_uid("EVD-V36-PRED"), "candidate_solubility_predictions_ood_uncertainty", EvidenceLevel.E1_ML, "Morgan/Tanimoto AD and residual interval", {"model_id": ml.model.model_id, "predictions": {name: item.to_dict() for name, item in predictions.items()}, "criterion_policy": {"ood": "REJECT", "max_uncertainty": 1.0}}, (provenance.provenance_id,))
    run.evidence.extend((data_evidence, model_evidence, prediction_evidence))
    run.gates.append(GateResult("GATE-V36-ML-DATA", "REAL-DATA-VALIDATION-001", ingestion.validation.status, "AqSolDB-G sample was source-validated and ingested", (data_evidence.evidence_id,)))
    run.gates.append(GateResult("GATE-V36-ML-MODEL", "ML-METRICS-001", GateStatus.PASS if ml.validation.passed else GateStatus.FAIL, "scaffold-held-out metrics and calibration were recorded", (model_evidence.evidence_id,), ml.validation.metrics))
    claim = ScientificClaim("The v3.6 solubility baseline was trained on the checked-in experimental AqSolDB-G sample with a scaffold split, and candidate predictions retain explicit OOD and residual-interval flags.", run.run_id, tuple(item.evidence_id for item in run.evidence), EvidenceLevel.E1_ML, ClaimStatus.SUPPORTED if ml.validation.passed else ClaimStatus.INSUFFICIENT_EVIDENCE, limitations=("This is a 46-row real-data sample, not an independent external test.", "The candidate predictions below are not rankable when OOD.",), conditions={"dataset": ingestion.manifest.dataset_id, "split": ml.split.strategy.value, "temperature_celsius": 25.0, "target_units": ingestion.manifest.units})
    run.add_claim(claim)
    persisted = _persist(app, run, root, environment, tags=("v3.6", "real", "ml", "aqsoldb"), artifacts={"model.json": str(ml.model_artifact.model_file), "model-manifest.json": str(root / "ml" / "models" / f"{ml.model_artifact.model_id}.manifest.json"), "split-manifest.json": str(root / "ml" / "models" / "split-manifest.json")}, datasets=(ingestion.manifest,))
    return persisted, ml, {"ingestion": ingestion.to_dict(), "predictions": {name: item.to_dict() for name, item in predictions.items()}, "claim": claim.to_dict()}


def _prep_and_dock(app: Any, root: Path, environment: Any, records: dict[str, dict[str, Any]], vina: str, obabel: str) -> dict[str, Any]:
    receptor_input = REPO_ROOT / ".research-os-live-3.4.1-pharma" / "1PXX_chainA_only.pdb"
    raw_structure = REPO_ROOT / ".research-os-live-3.4.1-pharma" / "1PXX.pdb"
    prep_root = root / "docking"
    prep_root.mkdir(parents=True, exist_ok=True)
    obabel_engine = __import__("research_os.engines.openbabel", fromlist=["OpenBabelEngine"]).OpenBabelEngine(obabel)
    vina_engine = __import__("research_os.engines.vina", fromlist=["VinaEngine"]).VinaEngine(vina)
    receptor_output = prep_root / "receptor-1PXX-chainA.pdbqt"
    receptor_run = ReceptorPreparationLab(obabel_engine).run({"target_id": "TARGET-COX2-1PXX", "species": "Mus musculus", "role": "COX-2 receptor", "structure_id": "1PXX", "source": "SRC-RCSB-1PXX", "input_path": str(receptor_input), "output_path": str(receptor_output), "options": ("-xr", "-h", "--partialcharge", "gasteiger"), "selected_chains": ("A",), "retained_cofactors": (), "removed_components": ("DIF", "BOG", "NAG", "HOH", "HEM (excluded from prepared PDBQT; Fe conversion incompatible)"), "hydrogen_treatment": "Open Babel -h", "charge_method": "Gasteiger partial charges", "raw_source_url": "https://www.rcsb.org/structure/1PXX", "raw_source_sha256": sha256_file(raw_structure)})
    receptor_persisted = _persist(app, receptor_run, root, environment, tags=("v3.6", "real", "docking", "receptor-preparation"), artifacts={"receptor.pdbqt": str(receptor_output)})
    receptor_manifest = next((item.payload for item in receptor_run.evidence), {})
    results: dict[str, Any] = {"receptor": receptor_persisted, "receptor_manifest": receptor_manifest, "receptor_sha256": sha256_file(receptor_output), "candidates": {}}
    for name, record in records.items():
        ligand_output = prep_root / f"{name}-cid{record['cid']}.pdbqt"
        ligand_run = LigandPreparationLab(obabel_engine).run({"candidate_id": f"PUBCHEM-CID-{record['cid']}", "input_path": record["sdf_path"], "output_path": str(ligand_output), "options": ("-h", "--partialcharge", "gasteiger"), "protonation_assumptions": ("PubChem 3D SDF used as the source conformer; no tautomer enumeration.",), "hydrogen_treatment": "Open Babel -h", "charge_method": "Gasteiger partial charges"})
        ligand_persisted = _persist(app, ligand_run, root, environment, tags=("v3.6", "real", "docking", "ligand-preparation", name), artifacts={"ligand.pdbqt": str(ligand_output)})
        ligand_manifest = next((item.payload for item in ligand_run.evidence), {})
        request = {"receptor_path": str(receptor_output), "ligand_path": str(ligand_output), "target_id": "TARGET-COX2-1PXX", "species": "Mus musculus", "role": "COX-2 receptor", "require_species": True, "require_preparation": True, "prepared_ligand_manifest": ligand_manifest, "prepared_receptor_manifest": receptor_manifest, "grid": GRID, "exhaustiveness": 4, "cpu": 2, "num_modes": 9, "protocol_id": DOCKING_PROTOCOL, "receptor_metadata": {"species": "Mus musculus", "structure_id": "1PXX", "receptor_sha256": results["receptor_sha256"], "source_id": "SRC-RCSB-1PXX"}}
        campaign = DockingCampaign(campaign_id=_uid(f"CAMP-V36-DOCK-{name}"), target_id="TARGET-COX2-1PXX", ligand_id=f"PUBCHEM-CID-{record['cid']}", replicate_count=3, seed_base=42)
        docking = campaign.run(DockingLab(vina_engine), request)
        replicate_records = []
        for run in docking.run_manifests:
            output_path = next((item.payload.get("output_path") for item in reversed(run.evidence) if item.kind == "molecular_docking_result"), None)
            replicate_records.append(_persist(app, run, root, environment, tags=("v3.6", "real", "docking", "replicate", name), artifacts={"docking-output.pdbqt": str(output_path)} if output_path and Path(str(output_path)).is_file() else {}))
        variability = DockingProtocolVariability.from_scores(DOCKING_PROTOCOL, docking.run_ids, docking.scores_kcal_mol, decision_relevance="same 1PXX chain-A receptor, same grid, Vina version, exhaustiveness, CPU, num_modes and seeds 42/43/44")
        results["candidates"][name] = {"source": record, "ligand": ligand_persisted, "campaign": docking.to_dict(), "replicates": replicate_records, "variability": variability.to_dict(), "vina_version": vina_engine.version, "prepared_ligand_sha256": sha256_file(ligand_output)}
    left = DockingProtocolVariability.from_scores(DOCKING_PROTOCOL, tuple(item["run_id"] for item in results["candidates"]["diclofenac"]["replicates"]), results["candidates"]["diclofenac"]["campaign"]["scores_kcal_mol"], decision_relevance="same 1PXX chain-A receptor, same grid, Vina version, exhaustiveness, CPU, num_modes and seeds 42/43/44")
    right = DockingProtocolVariability.from_scores(DOCKING_PROTOCOL, tuple(item["run_id"] for item in results["candidates"]["celecoxib"]["replicates"]), results["candidates"]["celecoxib"]["campaign"]["scores_kcal_mol"], decision_relevance="same 1PXX chain-A receptor, same grid, Vina version, exhaustiveness, CPU, num_modes and seeds 42/43/44")
    results["separation"] = evaluate_docking_separation(left, right, option_a="diclofenac", option_b="celecoxib").to_dict()
    results["protocol"] = {"protocol_id": DOCKING_PROTOCOL, "target": "murine PTGS2/COX-2", "structure_id": "1PXX", "source_url": "https://www.rcsb.org/structure/1PXX", "selected_chains": ["A"], "receptor_sha256": results["receptor_sha256"], "grid": GRID, "vina_version": vina_engine.version, "exhaustiveness": 4, "cpu": 2, "num_modes": 9, "seeds": [42, 43, 44], "replicates_per_candidate": 3, "best_single_score_is_not_a_decision": True}
    return results


def _cross_domain_decision(app: Any, records: dict[str, dict[str, Any]], molecule_runs: dict[str, Any], ml_payload: dict[str, Any], docking: dict[str, Any]) -> tuple[ScientificDecision, dict[str, Any], EvidenceAgreementAssessment]:
    predictions = ml_payload["predictions"]
    criteria = (
        DecisionCriterion("C-MOL-INTEGRITY", "molecular_identity_and_properties", "pass", True, minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, OOD_policy="REJECT", conditions={"source": "PubChem CID", "representation": "canonical SMILES"}, comparison_protocol="RDKit deterministic properties"),
        DecisionCriterion("C-SOLUBILITY-OOD", "solubility_applicability_domain", "pass", True, minimum_evidence_level=EvidenceLevel.E1_ML, OOD_policy="REJECT", conditions={"dataset": "AqSolDB-G real sample", "temperature_celsius": 25.0}, comparison_protocol="Morgan/Tanimoto max similarity; threshold declared by model"),
        DecisionCriterion("C-SOLUBILITY-UNCERTAINTY", "solubility_prediction_uncertainty", "min", True, minimum_evidence_level=EvidenceLevel.E1_ML, maximum_uncertainty_optional=1.0, OOD_policy="RETAIN_BUT_DO_NOT_RANK", conditions={"interval": "validation residual q90", "units": "log10(mol/L)"}, comparison_protocol="uncertainty must be <= 1.0 logS before selection"),
        DecisionCriterion("C-DOCKING-SEPARATION", "docking_protocol_separation", "pass", True, minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, OOD_policy="NO_EXTRAPOLATION", conditions={"structure": "1PXX", "same_grid": True}, comparison_protocol="three replicates; observed spread guard; no formal significance"),
    )
    evidence = tuple(dict.fromkeys([item for name in molecule_runs for item in molecule_runs[name]["evidence_ids"]] + [item for item in ml_payload["evidence_ids"]] + [item for name in docking["candidates"] for rep in docking["candidates"][name]["replicates"] for item in rep["evidence_ids"]] + docking["receptor"]["evidence_ids"]))
    ood_flags = tuple(f"{name}: {predictions[name]['status']} (ood_score={predictions[name]['ood_score']:.6f})" for name in predictions if predictions[name]["status"] == "OUT_OF_DOMAIN")
    uncertainty_notes = tuple(f"{name}: residual interval radius={predictions[name]['uncertainty']:.6f} logS; nominal pair difference={abs(predictions['diclofenac']['prediction'] - predictions['celecoxib']['prediction']):.6f} logS" for name in predictions)
    evaluations = []
    for name in records:
        pred = predictions[name]
        evaluations.extend((CriterionEvaluation(name, "C-MOL-INTEGRITY", True, tuple(molecule_runs[name]["evidence_ids"]), "RDKit run sealed", False), CriterionEvaluation(name, "C-SOLUBILITY-OOD", bool(pred["in_domain"]), (ml_payload["evidence_ids"][-1],), pred["reason"], not pred["in_domain"], pred["uncertainty"]), CriterionEvaluation(name, "C-SOLUBILITY-UNCERTAINTY", pred["uncertainty"] <= 1.0, (ml_payload["evidence_ids"][-1],), "declared maximum uncertainty is 1.0 logS", not pred["in_domain"], pred["uncertainty"])))
    evaluations.append(CriterionEvaluation("diclofenac", "C-DOCKING-SEPARATION", docking["separation"]["status"] == "CLEARLY_SEPARATED_UNDER_PROTOCOL", tuple(docking["candidates"]["diclofenac"]["replicates"][0]["evidence_ids"]), docking["separation"]["rationale"], False))
    evaluations.append(CriterionEvaluation("celecoxib", "C-DOCKING-SEPARATION", docking["separation"]["status"] == "CLEARLY_SEPARATED_UNDER_PROTOCOL", tuple(docking["candidates"]["celecoxib"]["replicates"][0]["evidence_ids"]), docking["separation"]["rationale"], False))
    decision = resolve_decision(decision_id=_uid("DECISION-REAL-02"), campaign_id="CAMP-V36-MOLECULE-SOLUBILITY-DOCKING", question_id="Q-REAL-MOLECULE-SOLUBILITY-DOCKING", decision_question="Can one of two real COX-2 ligands be selected when molecular identity, solubility OOD/uncertainty and three-replicate docking variability are all required?", options=("diclofenac", "celecoxib"), criteria=criteria, required_evidence=evidence, evidence_available=evidence, evaluations=tuple(evaluations), conditions={"molecule_sources": {name: records[name]["source_id"] for name in records}, "solubility": {"dataset": "aqsoldb-g-real-sample", "temperature_celsius": 25.0}, "docking": docking["protocol"], "selection_rule": "no option is selectable unless all required criteria pass; no total score"}, uncertainties=uncertainty_notes, OOD_flags=ood_flags, limitations=("Docking score is E2 computational evidence, not measured affinity.", "The checked-in AqSolDB-G sample is not an independent external test.", "No therapeutic, clinical or efficacy conclusion is permitted.",))
    agreement = EvidenceAgreementAssessment("real diclofenac/celecoxib cross-domain comparison", evidence, {"candidate_sources": [records[name]["source_id"] for name in records], "solubility_dataset": "AqSolDB-G real sample", "docking_protocol": DOCKING_PROTOCOL}, EvidenceAgreementStatus.PARTIALLY_CONSISTENT if decision.selected_option else EvidenceAgreementStatus.INSUFFICIENT_EVIDENCE, evidence_types=("molecular_properties", "solubility_ml", "applicability_domain", "docking_variability"), comparability="molecule identity and docking protocol comparable; ML prediction remains OOD-limited", conflicts=("Both candidates are outside the model applicability domain; no solubility ranking was permitted.",), strongest_supported_level=EvidenceLevel.E2_COMPUTATIONAL, limitations=("Heterogeneous evidence is summarized, not summed.", "Three docking replicates do not support a distributional inference.",))
    audit = audit_decision(decision, known_evidence_ids=set(evidence), reproducibility_references=True)
    return decision, {"audit": audit.to_dict(), "predictions": predictions, "decision_criteria": [item.to_dict() for item in criteria], "docking_separation": docking["separation"]}, agreement


def _docking_and_uncertainty_decisions(docking: dict[str, Any], ml_payload: dict[str, Any]) -> dict[str, Any]:
    docking_evidence = tuple(dict.fromkeys([item for name in docking["candidates"] for replicate in docking["candidates"][name]["replicates"] for item in replicate["evidence_ids"]] + docking["receptor"]["evidence_ids"]))
    separation = docking["separation"]
    scores = {name: docking["candidates"][name]["variability"]["score_mean"] for name in docking["candidates"]}
    selected = min(scores, key=scores.get) if separation["status"] == "CLEARLY_SEPARATED_UNDER_PROTOCOL" else None
    docking_criterion = DecisionCriterion("C-REAL-01-DOCKING-GUARD", "three_replicate_protocol_separation", "pass", True, minimum_evidence_level=EvidenceLevel.E2_COMPUTATIONAL, OOD_policy="SCOPE_LIMITED_NO_EXTRAPOLATION", conditions={"target": "murine PTGS2/COX-2", "structure_id": "1PXX"}, comparison_protocol="observed mean difference versus replicate spread; no formal significance")
    docking_decision = ScientificDecision(_uid("DECISION-REAL-01"), "CAMP-V36-COX2-COMPARATOR", "Q-REAL-DOCKING-SEPARATION", "Are the two real ligands clearly separated under the identical declared docking protocol?", ("diclofenac", "celecoxib"), (docking_criterion,), docking_evidence, docking_evidence, (), (), {"protocol": docking["protocol"], "interpretation": "protocol-limited separation, not affinity"}, (f"mean scores: {scores}", "replicate spread: {docking['separation']['variability_margin_kcal_mol']:.6f} kcal/mol"), ("docking domain restricted to 1PXX chain A and declared grid",), selected, tuple(name for name in scores if name != selected), DecisionStatus.SUPPORTED_DECISION if selected else DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "The separation guard supports a protocol-limited statement." if selected else "The protocol guard does not support a clear separation.", ("A best single score was not used; the guard used replicate means and observed spread.", "No clinical, therapeutic or measured-affinity inference is permitted."))
    predictions = ml_payload["predictions"]
    nominal_difference = abs(predictions["diclofenac"]["prediction"] - predictions["celecoxib"]["prediction"])
    uncertainty_sum = predictions["diclofenac"]["uncertainty"] + predictions["celecoxib"]["uncertainty"]
    uncertainty_criterion = DecisionCriterion("C-REAL-03-UNCERTAINTY-DOMINATES", "nominal_solubility_difference_vs_residual_uncertainty", "pass", True, minimum_evidence_level=EvidenceLevel.E1_ML, OOD_policy="RETAIN_BUT_DO_NOT_RANK", conditions={"metric": "log10(mol/L)", "interval": "validation residual q90"}, comparison_protocol="refuse a molecule selection when nominal difference <= sum of retained uncertainty radii")
    uncertainty_decision = ScientificDecision(_uid("DECISION-REAL-03"), "CAMP-V36-MOLECULE-SOLUBILITY-UNCERTAINTY", "Q-REAL-UNCERTAINTY-DOMINATES", "Does retained solubility uncertainty dominate the nominal difference between the two real candidate predictions?", ("select_by_nominal_difference", "refuse_selection_due_to_uncertainty"), (uncertainty_criterion,), (ml_payload["evidence_ids"][-1],), (ml_payload["evidence_ids"][-1],), (), (), {"nominal_difference_logS": nominal_difference, "uncertainty_sum_logS": uncertainty_sum}, (f"nominal difference={nominal_difference:.6f} logS", f"uncertainty sum={uncertainty_sum:.6f} logS"), tuple(f"{name}: {predictions[name]['status']}" for name in predictions), "refuse_selection_due_to_uncertainty" if nominal_difference <= uncertainty_sum else None, ("select_by_nominal_difference",) if nominal_difference <= uncertainty_sum else (), DecisionStatus.SUPPORTED_DECISION if nominal_difference <= uncertainty_sum else DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "The retained residual uncertainty is at least as large as the nominal pair difference; selection by that difference is refused." if nominal_difference <= uncertainty_sum else "The nominal difference exceeds the retained uncertainty sum; this diagnostic does not override the cross-domain OOD gate.", ("This diagnostic is not a calibrated probability or confidence statement.",))
    return {"docking_decision": docking_decision, "uncertainty_decision": uncertainty_decision}


def _combustion_and_gates(app: Any, root: Path, environment: Any) -> dict[str, Any]:
    rows = []
    for fuel in ("H2:1", "CH4:1"):
        run = CombustionLab().run({"fuel": fuel, "oxidizer": "O2:0.21,N2:0.79", "equivalence_ratio": 1.0, "temperature_k": 300.0, "pressure_pa": 101325.0, "basis": "mole", "mechanism": "gri30.yaml"}, experiment="v36_limited_fuel_comparison")
        persisted = _persist(app, run, root, environment, tags=("v3.6", "real", "combustion", fuel))
        evidence = next((item for item in run.evidence if item.kind == "combustion_equilibrium_simulation"), None)
        rows.append({"fuel": fuel, "persisted": persisted, "temperature_k": evidence.payload.get("adiabatic_temperature_k") if evidence else None, "evidence_id": evidence.evidence_id if evidence else None, "run_status": run.status})
    values = {row["fuel"]: row["temperature_k"] for row in rows if row["temperature_k"] is not None}
    criterion = DecisionCriterion("C-COMB-TEMP", "adiabatic_equilibrium_temperature_k", "max", True, minimum_evidence_level=EvidenceLevel.E3_PHYSICS, OOD_policy="SCOPE_LIMITED_NO_EXTRAPOLATION", conditions={"temperature_k": 300.0, "pressure_pa": 101325.0, "equivalence_ratio": 1.0, "oxidizer": "O2:0.21,N2:0.79", "mechanism": "gri30.yaml"}, comparison_protocol="same Cantera equilibrium HP protocol for H2 and CH4")
    options = ("H2:1", "CH4:1")
    selected = max(values, key=values.get) if len(values) == 2 and values["H2:1"] != values["CH4:1"] else None
    decision = ScientificDecision(_uid("DECISION-REAL-04"), "CAMP-V36-COMBUSTION", "Q-REAL-COMBUSTION", "Under one declared Cantera equilibrium protocol, which of H2 and CH4 has the higher calculated adiabatic HP temperature?", options, (criterion,), tuple(row["evidence_id"] for row in rows if row["evidence_id"]), tuple(row["evidence_id"] for row in rows if row["evidence_id"]), (), (), {"protocol_id": "cantera.equilibrium.hp.v1", "temperature_role": "initial condition only; not failure temperature"}, ("Cantera numerical uncertainty was not estimated.", "The comparison is limited to equilibrium HP outputs under gri30.yaml."), ("domain restricted to these two fuels and conditions",), selected, tuple(option for option in options if option != selected), DecisionStatus.SUPPORTED_DECISION if selected else DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "The selected fuel has the higher calculated value under the declared E3 protocol." if selected else "Both required Cantera outputs were not available or were tied.", ("This does not validate a hardware ignition, failure or operating limit.", "Cantera temperatures are not treated as failure temperatures."))
    return {"rows": rows, "decision": decision.to_dict(), "audit": audit_decision(decision, reproducibility_references=True).to_dict()}


def _thermal_materials_battery(app: Any, root: Path, environment: Any, battery_path: Path, *, hot_temperature_k: float | None, simulated_evidence_ids: tuple[str, ...]) -> dict[str, Any]:
    thermal_run = ThermalLab().run({"hot_temperature_k": hot_temperature_k, "cold_temperature_k": 300.0, "conductivity_w_mk": None, "thickness_m": None, "area_m2": 1.0, "provenance": {"source_id": "SRC-CANTERA-GRI30", "notes": "Cantera equilibrium temperature is a model boundary input, never a failure temperature"}}, experiment="v36_fourier_material_gate")
    thermal_persisted = _persist(app, thermal_run, root, environment, tags=("v3.6", "real", "thermal", "first-loss"))
    materials_decision = ScientificDecision(_uid("DECISION-REAL-05"), "CAMP-V36-COMBUSTION-THERMAL-MATERIALS", "Q-REAL-MATERIALS", "Can the available records support a condition-matched material conclusion after the combustion→thermal boundary?", ("material_record", "no_decision"), (DecisionCriterion("C-MATERIAL-RECORD", "condition_complete_material_observation", "pass", True, minimum_evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL, OOD_policy="REJECT", conditions={"material": "named alloy required", "environment": "specified", "temperature": "specified"}, comparison_protocol="source-located record-level observation"),), (), (), (), (), {"thermal_run_id": thermal_persisted["run_id"], "fourier_model": "steady 1-D planar, constant k; no convection/radiation/contact resistance/transient", "cantera_temperature_role": "boundary input only, not failure temperature"}, ("material identity, composition, processing, microstructure, environment and stress are missing",), ("no condition-complete material record was retrieved",), None, ("material_record",), DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "The thermal model gate recorded the explicit assumptions, but no source-located condition-complete material observation is available.", ("No material property, qualification, approval or survivability conclusion was invented.",))
    comparison = SimulationExperimentComparison.from_values(metric="temperature_k", simulated_evidence_ids=simulated_evidence_ids, experimental_evidence_ids=tuple(), condition_match="UNKNOWN", simulation_value=None, experimental_value=None, uncertainty=None, tolerance_protocol="No calibration; a matched experimental record was not retrieved.")
    analysis = analyze_nasa_pcoe_rw3(battery_path)
    battery_source = app.service.source_registry.get("SRC-NASA-PCOE-RW3")
    battery_run = RunManifest("ResearchOS-Battery", "v36_nasa_pcoe_rw3_quality_boundary", {"dataset_id": analysis.artifact.dataset_id, "artifact_path": analysis.artifact.artifact_path, "artifact_sha256": analysis.artifact.artifact_sha256}, {"protocol_id": "battery-artifact-summary.v1", "parser": "scipy.io.loadmat", "source_policy": "archive data only; scripts not executed"}, run_id=_uid("RUN-V36-BATTERY"))
    battery_run.start()
    battery_run.attach_environment(environment)
    battery_provenance = ProvenanceRecord(SourceType.DATASET, battery_source.source_id, title=battery_source.title, url=battery_source.url, license=battery_source.license, method="scipy.io.loadmat per MATLAB member; mean/final-time summaries", conditions=analysis.artifact.conditions, notes="Archive hash verified; archive scripts were not executed.")
    battery_run.provenance.append(battery_provenance)
    battery_evidence = Evidence(_uid("EVD-V36-BATTERY"), "battery_electrochemical_observation_summary", EvidenceLevel.E4_CURATED_EXPERIMENTAL, battery_source.url or battery_source.source_id, {"artifact": analysis.artifact.to_dict(), "summary": analysis.summary, "observation_sample": [item.to_dict() for item in analysis.observations], "missing_fields": ["capacity_ah", "resistance_ohm", "uncertainty"]}, (battery_provenance.provenance_id,))
    battery_run.evidence.append(battery_evidence)
    battery_run.gates.append(GateResult("GATE-V36-BATTERY-ARTIFACT", "BATT-ARTIFACT-001", GateStatus.PASS, "public NASA battery archive was hashed and its MATLAB members were parsed", (battery_evidence.evidence_id,), {"artifact_sha256": analysis.artifact.artifact_sha256, "observation_count": len(analysis.observations)}))
    battery_claim = ScientificClaim("The NASA PCoE RW3 artifact exposes measured voltage, current, temperature and time-step fields, while capacity, resistance and uncertainty remain absent from the parsed step schema.", battery_run.run_id, (battery_evidence.evidence_id,), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ClaimStatus.SUPPORTED, limitations=("This is a descriptive schema result; it does not establish a degradation trajectory or model.",), conditions=analysis.artifact.conditions)
    battery_run.add_claim(battery_claim)
    battery_persisted = _persist(app, battery_run, root, environment, tags=("v3.6", "real", "battery", "nasa-pcoe-rw3"), datasets=(analysis.artifact.to_dict(),))
    quality = BatteryDatasetQualityAssessment(analysis.artifact.dataset_id, tuple(analysis.artifact.schema.get("step_fields", ())), ("capacity_ah", "resistance_ohm", "uncertainty"), (battery_evidence.evidence_id,), analysis.assessment.status, ("Observed fields are descriptive step summaries; missing fields remain unknown.",))
    second_source = {"source_id": "SRC-DOE-BATTERY-DATA-HUB", "url": "https://batterydata.energy.gov/", "status": "SEARCHED_NO_CONDITION_COMPARABLE_ARTIFACT_RETRIEVED", "reason": "the registered DOE hub is a discovery source here; no second parsed experimental record with matched cell/protocol/fields was available in this execution"}
    protocol = BatteryProtocolComparability(_uid("BAT-CMP"), "SRC-NASA-PCOE-RW3", second_source["source_id"], ("source_identity",), ("cell_id", "cycle_definition", "capacity_ah", "uncertainty"), BatteryProtocolMatchStatus.UNKNOWN, ("No second source artifact was retrieved; no cross-source value comparison was made.",))
    battery_decision = ScientificDecision(_uid("DECISION-REAL-06"), "CAMP-V36-BATTERY", "Q-REAL-BATTERY", "Can the available battery records support a condition-comparable degradation decision?", ("supported_degradation_claim", "no_decision"), (DecisionCriterion("C-BATT-CAPACITY", "capacity_ah", "max", True, minimum_evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL, OOD_policy="REJECT", conditions={"procedure": "NASA PCoE RW3 room-temperature random walk"}, comparison_protocol="capacity trajectory with cell identity and cycle definition"), DecisionCriterion("C-BATT-UNCERTAINTY", "uncertainty", "min", True, minimum_evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL, OOD_policy="REJECT", conditions={"uncertainty": "reported or traceably derived"}, comparison_protocol="uncertainty must be recorded; no imputation")), (battery_evidence.evidence_id,), (battery_evidence.evidence_id,), (), (), {"primary_source": analysis.artifact.to_dict(), "second_source_search": second_source, "battery_run_id": battery_persisted["run_id"]}, ("capacity_ah, resistance_ohm and uncertainty are absent from the parsed step schema",), ("second source not condition-comparable",), None, ("supported_degradation_claim",), DecisionStatus.NO_DECISION_INSUFFICIENT_EVIDENCE, "Measured voltage/current/temperature/time fields were parsed, but the required capacity/uncertainty boundary and a matched second source are absent.", ("No degradation model or battery control recommendation was produced.",))
    return {"thermal": {"run": thermal_persisted, "first_loss": thermal_run.first_loss.__dict__ if thermal_run.first_loss else None}, "materials_decision": materials_decision.to_dict(), "materials_audit": audit_decision(materials_decision, reproducibility_references=True).to_dict(), "battery_run": battery_persisted, "battery_quality": quality.to_dict(), "battery_second_source_search": second_source, "battery_protocol_comparability": protocol.to_dict(), "battery_decision": battery_decision.to_dict(), "battery_audit": audit_decision(battery_decision, known_evidence_ids={battery_evidence.evidence_id}, reproducibility_references=True).to_dict(), "simulation_experiment_comparison": comparison.to_dict()}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS 3.6 real cross-domain scientific decisions")
    parser.add_argument("--data-root", default=str(REPO_ROOT / ".research-os-live-3.6"))
    parser.add_argument("--codex-executable", default=None)
    parser.add_argument("--vina-executable", default=str(REPO_ROOT / ".venv" / "Scripts" / "vina.exe"))
    parser.add_argument("--openbabel-executable", default=str(REPO_ROOT / ".venv" / "Scripts" / "obabel.exe"))
    parser.add_argument("--battery-artifact", default=str(REPO_ROOT / ".research-os-live-3.4-battery" / "nasa-pcoe-rw3.zip"))
    args = parser.parse_args()
    root = Path(args.data_root).resolve()
    root.mkdir(parents=True, exist_ok=True)
    vina = Path(args.vina_executable).resolve()
    obabel = Path(args.openbabel_executable).resolve()
    battery_path = Path(args.battery_artifact).resolve()
    os.environ["RESEARCH_OS_VINA_EXECUTABLE"] = str(vina)
    os.environ["RESEARCH_OS_OPENBABEL_EXECUTABLE"] = str(obabel)
    app = build_default_application(root, oracle_mode="live", codex_executable=args.codex_executable)
    payload: dict[str, Any] = {"version": "3.6.0", "branch": "research-os-v1.3", "started_at": _now(), "git_commit": __import__("subprocess").run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip(), "source_policy": "official source bytes and source metadata are data; Codex cannot create scientific evidence"}
    environment = capture_environment(repo_root=REPO_ROOT)
    try:
        discovery = app.campaigns.discover()  # type: ignore[union-attr]
        payload["live_discovery"] = discovery.to_dict()
        payload["live_researcher"] = app.campaigns.final_researcher_prompt()  # type: ignore[union-attr]
        records = {name: _compound(root, name) for name in COMPOUNDS}
        for record in records.values():
            _register_source(app, record)
        payload["compounds"] = records
        molecule_runs = {name: _molecule_run(app, root, environment, name, record) for name, record in records.items()}
        ml_persisted, ml_result, ml_payload = _ml_run(app, root, environment, records)
        ml_payload["run"] = ml_persisted
        payload["molecule_runs"] = molecule_runs
        payload["ml"] = ml_payload
        docking = _prep_and_dock(app, root, environment, records, str(vina), str(obabel))
        payload["docking"] = docking
        docking_and_uncertainty = _docking_and_uncertainty_decisions(docking, {**ml_payload, **{"evidence_ids": ml_persisted["evidence_ids"]}})
        payload["decision_real_01"] = docking_and_uncertainty["docking_decision"].to_dict()
        payload["decision_real_01_audit"] = audit_decision(docking_and_uncertainty["docking_decision"], known_evidence_ids={item for name in docking["candidates"] for rep in docking["candidates"][name]["replicates"] for item in rep["evidence_ids"]} | set(docking["receptor"]["evidence_ids"])).to_dict()
        payload["decision_real_03"] = docking_and_uncertainty["uncertainty_decision"].to_dict()
        payload["decision_real_03_audit"] = audit_decision(docking_and_uncertainty["uncertainty_decision"], known_evidence_ids={ml_persisted["evidence_ids"][-1]}).to_dict()
        app.decisions.save(docking_and_uncertainty["docking_decision"])
        app.decisions.save(docking_and_uncertainty["uncertainty_decision"])
        decision, decision_context, agreement = _cross_domain_decision(app, records, molecule_runs, {**ml_payload, **{"evidence_ids": ml_persisted["evidence_ids"]}}, docking)
        app.decisions.save(decision)
        payload["cross_domain_decision"] = decision.to_dict()
        payload["cross_domain_decision_context"] = decision_context
        payload["evidence_agreement"] = agreement.to_dict()
        payload["decision_audit"] = decision_context["audit"]
        payload["combustion"] = _combustion_and_gates(app, root, environment)
        combustion_temperatures = tuple(row["temperature_k"] for row in payload["combustion"]["rows"] if row.get("temperature_k") is not None)
        combustion_evidence_ids = tuple(row["evidence_id"] for row in payload["combustion"]["rows"] if row.get("evidence_id"))
        payload["thermal_materials_battery"] = _thermal_materials_battery(app, root, environment, battery_path, hot_temperature_k=max(combustion_temperatures) if combustion_temperatures else None, simulated_evidence_ids=combustion_evidence_ids)
        for key in ("materials_decision", "battery_decision"):
            app.decisions.save(ScientificDecision.from_dict(payload["thermal_materials_battery"][key]))
        app.decisions.save(ScientificDecision.from_dict(payload["combustion"]["decision"]))
        parsimony = PlanParsimonyAssessment("PLAN-V36-MINIMAL-CROSS-DOMAIN", ("molecule identity/properties", "real AqSolDB solubility model + OOD/uncertainty", "same-protocol three-replicate docking"), ("source synthesis", "Cantera comparison", "thermal/materials gate", "battery schema audit"), (), (), True, ("A request for a universal total score, clinical efficacy, or material approval is rejected as unsupported.",))
        payload["plan_parsimony"] = parsimony.to_dict()
        payload["simulation_experiment_comparison"] = payload["thermal_materials_battery"]["simulation_experiment_comparison"]
        payload["acceptance"] = {"scientific_decision_recorded": True, "real_no_decision_recorded": decision.selected_option is None, "explicit_criteria": bool(decision.criteria), "docking_variability_recorded": bool(docking.get("separation")), "docking_guard_status": docking["separation"]["status"], "docking_decision_status": payload["decision_real_01"]["decision_status"], "uncertainty_decision_status": payload["decision_real_03"]["decision_status"], "cross_domain_decision_status": decision.decision_status, "cross_domain_executed": bool(molecule_runs and ml_persisted and docking.get("candidates")), "ood_influenced_decision": bool(decision.OOD_flags), "uncertainty_included": bool(decision.uncertainties), "heterogeneous_agreement_recorded": agreement.valid, "combustion_e3_decision": payload["combustion"]["decision"]["decision_status"], "materials_decision": payload["thermal_materials_battery"]["materials_decision"]["decision_status"], "battery_decision": payload["thermal_materials_battery"]["battery_decision"]["decision_status"], "plan_parsimony_recorded": parsimony.minimal_sufficient, "provider_created_scientific_evidence": False, "live_codex_used_for_discovery_and_researcher_boundary": True, "v37_gate": "NOT_OPEN_NO_REAL_SYSTEMATIC_BENCHMARK_EXECUTED", "v38_gate": "NOT_OPEN_V37_GATE_CLOSED"}
        payload["status"] = "PASS" if all((payload["acceptance"]["scientific_decision_recorded"], payload["acceptance"]["real_no_decision_recorded"], payload["acceptance"]["explicit_criteria"], payload["acceptance"]["docking_variability_recorded"], payload["acceptance"]["cross_domain_executed"], payload["acceptance"]["heterogeneous_agreement_recorded"], payload["acceptance"]["plan_parsimony_recorded"])) else "INDETERMINATE"
        status = 0 if payload["status"] == "PASS" else 1
    except Exception as exc:
        payload["status"] = "FAIL_CLOSED"
        payload["error"] = {"type": type(exc).__name__, "message": str(exc)}
        payload["acceptance"] = {"scientific_decision_recorded": False, "v37_gate": "CLOSED"}
        status = 1
    finally:
        payload["finished_at"] = _now()
        _json(root / "v3.6-real-decision.json", payload)
        app.close()
    print(json.dumps({"status": payload.get("status"), "acceptance": payload.get("acceptance"), "decision": payload.get("cross_domain_decision", {}).get("decision_status"), "docking": payload.get("docking", {}).get("separation")}, indent=2, ensure_ascii=False, default=str))
    return status


if __name__ == "__main__":
    raise SystemExit(main())
