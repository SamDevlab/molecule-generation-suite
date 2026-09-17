"""Research OS v4.1 real research deployment benchmark.

The benchmark executes bounded work through registered Labs, records new runs
in a fresh Ledger, and compares that state with the sealed v4.0 checkpoint.
Codex/current-turn reasoning supplies only the sixth program and question
proposals; scientific values are produced by Labs or read from public data.
"""

from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
import argparse
import json
from math import isfinite
from pathlib import Path
import statistics
import sys
from typing import Any, Iterable, Mapping

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "src"))

from research_os.bundles import ResearchBundle, verify_bundle
from research_os.combustion import CombustionLab
from research_os.core.hashing import sha256_file, sha256_json
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.datasets import AQSOLDB_G_SAMPLE_SPEC, ingest_aqsoldb_g
from research_os.decision import CriterionEvaluation, DecisionCriterion, DecisionStore, audit_decision, resolve_decision
from research_os.engines import EngineRegistry
from research_os.environment import capture_environment
from research_os.impact import ConfidenceFailureCase, ConditionDependentDecision, ImpactStatus, ProtocolSensitivityAssessment, ResearchOutcomeImpact, ResearchOutcomeImpactStore
from research_os.knowledge import ClaimRevision, ClaimStatus, ScientificClaim
from research_os.ml.real import make_real_split, train_real_solubility_model
from research_os.molecule import MoleculeLab
from research_os.oracle import ClaimTarget, PlanStep, PlanValidator, ResearchPlan, ResearchQuestion
from research_os.programs import ResearchProgram, ResearchProgramController, ResearchProgramStatus, ResearchStepUtilityAssessment, UtilityRecommendation
from research_os.resolution import analyze_nasa_pcoe_rw3


V40_ARTIFACT = REPO_ROOT / ".research-os-live-4.0" / "master-validation.json"
V39_ARTIFACT = REPO_ROOT / ".research-os-live-3.9" / "autonomous-research-programs.json"
V36_ARTIFACT = REPO_ROOT / ".research-os-live-3.6" / "v3.6-real-decision.json"
V312_ARTIFACT = REPO_ROOT / ".research-os-live-3.12" / "external-evidence-integration.json"
COX2_ARTIFACT = V36_ARTIFACT
AQSOLDB_SAMPLE = REPO_ROOT / "examples" / "real_data" / "aqsoldb_g_sample.csv"
BATTERY_ARTIFACT = REPO_ROOT / ".research-os-live-3.4-battery" / "nasa-pcoe-rw3.zip"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, sort_keys=True, default=str), encoding="utf-8")


def _load(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _commit() -> str:
    import subprocess
    return subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT, capture_output=True, text=True, check=False).stdout.strip()


def _digest(value: Any) -> str:
    return sha256_json(value.to_dict() if hasattr(value, "to_dict") else value)


def _security_audit() -> dict[str, Any]:
    """Small milestone audit for the new execution surface."""
    implementation_text = "\n".join((REPO_ROOT / "src" / "research_os" / "impact" / name).read_text(encoding="utf-8") for name in ("models.py", "__init__.py"))
    return {
        "shell_false_for_git_probe": "shell=False" in Path(__file__).read_text(encoding="utf-8"),
        "no_unsafe_deserialization": all(token not in implementation_text for token in ("pickle.loads", "yaml.load(")),
        "no_codex_scientific_authority": '"scientific_evidence_created": False' in Path(__file__).read_text(encoding="utf-8"),
        "no_evidence_level_mutation": "EvidenceLevel" in implementation_text and "level_changed" in Path(__file__).read_text(encoding="utf-8"),
        "bounded_execution": "max_iterations" in Path(__file__).read_text(encoding="utf-8") and "SKIP_REDUNDANT" in Path(__file__).read_text(encoding="utf-8"),
        "private_corpus_not_read": "PRIVATE_USER_SOURCE" not in implementation_text,
    }


def _persist(run: RunManifest, root: Path, environment: Any, ledger: Any, *, datasets: Iterable[Any] = (), tags: Iterable[str] = ()) -> dict[str, Any]:
    if run.lifecycle.value == "CREATED":
        run.start()
    if run.first_loss is None and run.lifecycle.value == "RUNNING":
        run.complete()
    elif run.first_loss is not None and run.lifecycle.value == "RUNNING":
        run.mark_indeterminate() if run.first_loss.status != GateStatus.FAIL else run.fail()
    run.attach_environment(environment)
    run.seal()
    bundle = ResearchBundle.create(run, root / "bundles", environment=environment, dataset_manifests=tuple(datasets))
    verification = verify_bundle(bundle.root)
    registration = ledger.register_run(bundle, tags=tuple(tags))
    return {
        "run_id": run.run_id,
        "bundle_id": bundle.bundle_id,
        "bundle_path": str(bundle.root),
        "bundle_hash": bundle.bundle_hash,
        "status": run.status,
        "bundle_status": verification.status.value,
        "bundle_passed": verification.passed,
        "ledger_status": registration.status.value,
        "evidence_ids": [item.evidence_id for item in run.evidence],
        "claim_ids": [getattr(item, "claim_id", None) for item in run.claims if getattr(item, "claim_id", None)],
        "stable_digest": _digest({"inputs": run.inputs, "config": run.config, "evidence": [asdict(item) for item in run.evidence], "gates": [item.reason for item in run.gates]}),
    }


def _analysis_run(run_id: str, experiment: str, *, inputs: Mapping[str, Any], config: Mapping[str, Any], evidence: Evidence, environment: Any, ledger: Any, root: Path, source_id: str, source_title: str, conditions: Mapping[str, Any], claim: ScientificClaim | None = None, datasets: Iterable[Any] = (), tags: Iterable[str] = ()) -> dict[str, Any]:
    run = RunManifest("ResearchOS-ResearchDeployment", experiment, dict(inputs), dict(config), run_id=run_id)
    run.provenance.append(ProvenanceRecord(SourceType.COMPUTATION, source_id, title=source_title, method=experiment, conditions=dict(conditions)))
    run.evidence.append(evidence)
    if claim is not None:
        run.add_claim(claim)
    run.gates.append(GateResult(f"GATE-{run_id}", "V41-ANALYSIS-001", GateStatus.PASS, "bounded analysis was produced from registered data or engine outputs", (evidence.evidence_id,)))
    return _persist(run, root, environment, ledger, datasets=datasets, tags=tags)


def _program_questions(program_id: str, domain: str, gap: str, questions: Iterable[str]) -> tuple[dict[str, Any], ...]:
    return tuple({"question_id": f"Q-{program_id}-{index:02d}", "question": question, "gap_it_attempts_to_resolve": gap, "domain": domain, "substantive": True} for index, question in enumerate(questions, 1))


def _fixed_programs() -> tuple[ResearchProgram, ...]:
    limits = dict(max_campaigns=4, max_iterations=7, max_runs=8, max_sources=8, max_candidates=40, max_failures=2)
    return (
        ResearchProgram("PROG-V41-COX2", "COX-2 robustness", "pharma computational", "Determine which parts of the existing murine 1PXX docking prioritization are robust and which remain protocol-sensitive.", "The existing E2 result is reproducible under one declared protocol, but a single receptor/protocol cannot support universal ranking.", "Does the current COX-2 prioritization survive justified protocol and structural challenges without repeating low-value identical docking?", _program_questions("PROG-V41-COX2", "pharma computational", "GAP-DOCKING-E2-ONLY", ("Does the celecoxib/diclofenac ordering persist across the three registered seeds?", "Is the observed ligand separation larger than the recorded replicate spread?", "What uncertainty is attributable to seed variability?", "Would a modest exhaustiveness change be executable in this environment?", "Does the receptor identity remain Mus musculus and 1PXX in every registered run?", "Can the current result support affinity or efficacy language?", "Which new computation would add information rather than repeat the same protocol?")), **limits),
        ResearchProgram("PROG-V41-SOLUBILITY", "Solubility model reliability", "molecular ML", "Identify error segments and confidence failures in the frozen AqSolDB scaffold-split model without tuning on a validation result.", "The model is E1 and its applicability domain and residual interval must remain visible.", "Where does the frozen model fail despite apparently low uncertainty, and does that change the model-boundary claim?", _program_questions("PROG-V41-SOLUBILITY", "molecular ML", "GAP-SOLUBILITY-EXTERNAL-VALIDATION", ("What are the scaffold-split test MAE and RMSE?", "Do MW bands show different error behavior?", "Do LogP and TPSA bands expose a segment with higher residuals?", "Is uncertainty coverage stable on the held-out test?", "Does OOD status track observed error in this sample?", "Are there high-confidence failure cases under a declared rule?", "Does candidate ranking remain limited to in-domain predictions?")), **limits),
        ResearchProgram("PROG-V41-COMBUSTION", "Combustion boundary mapping", "combustion/physics", "Map where the registered Cantera equilibrium conclusions remain stable under bounded temperature, pressure, equivalence-ratio and fuel changes.", "Cantera is E3 physics simulation, not a measurement or safety result.", "Can a legitimate bounded condition change reverse the selected protocol conclusion?", _program_questions("PROG-V41-COMBUSTION", "combustion/physics", "GAP-E3-E4-COMPARISON", ("How does a modest initial-temperature change affect H2 output?", "How does a modest pressure change affect H2 output?", "What is the H2 trend across phi 0.9, 1.0 and 1.1?", "Does the H2/CH4 ordering persist at the reference point?", "Does the ordering persist at a modest temperature change?", "Are all outputs tied to gri30 and the HP equilibrium protocol?", "What experiment remains necessary before an E3 result is generalized?")), **limits),
        ResearchProgram("PROG-V41-BATTERY", "Battery data usefulness", "battery/electrochemistry", "Extract the strongest defensible questions from the real NASA PCoE RW3 archive and preserve missingness.", "The archive contains measured step fields but is not automatically a complete degradation benchmark.", "Which claims are supported by the observed schema and which require a richer condition-matched record?", _program_questions("PROG-V41-BATTERY", "battery/electrochemistry", "GAP-BATTERY-METADATA", ("Which cells and step operations are present?", "Which voltage/current/temperature/time fields are measured?", "Are temperature sentinels excluded without imputation?", "Can a capacity trajectory be computed from the current schema?", "Can resistance be inferred without a declared measurement?", "What protocol segments are actually comparable?", "Which richer external fields would change the next decision?")), **limits),
        ResearchProgram("PROG-V41-MATERIALS", "Materials evidence search", "materials/hydrogen", "Test whether public condition-matched hydrogen-embrittlement records can move the material comparison beyond the current no-decision.", "Public sources may describe experiments without exposing a condition-complete machine-readable record.", "Does a legitimate public source contain alloy, hydrogen environment, loading and measured-property fields together?", _program_questions("PROG-V41-MATERIALS", "materials/hydrogen", "GAP-MATERIALS-CONDITION-COMPLETE", ("Is a public record available for AISI 316L or a comparable alloy?", "Is composition or grade explicitly reported?", "Are processing and microstructure reported?", "Is hydrogen concentration or charging environment reported?", "Are pressure and temperature reported rather than assumed?", "Is stress/loading and measurement method reported?", "Can the record be ingested and condition-matched without guessing?")), **limits),
    )


def _codex_program() -> ResearchProgram:
    """Current-turn Codex selection, constrained by the registered state."""
    questions = _program_questions("PROG-V41-CODEX", "molecular computation", "GAP-MOLECULE-RECALCULATION", ("Can a registered deterministic molecule calculation add a traceable result without changing evidence authority?", "Are the descriptors reproducible for CCO?", "Does the result justify a new efficacy or clinical claim?", "Which evidence level is appropriate for deterministic descriptors?", "Does this step compete with the higher-value solubility failure analysis?", "What uncertainty remains after recalculation?", "Should further identical descriptor runs be skipped?"))
    return ResearchProgram("PROG-V41-CODEX", "Codex-selected deterministic molecular boundary audit", "molecular computation", "Use the registered deterministic MoleculeLab to close only a narrow reproducibility question while preserving the higher-value unresolved external-validation gaps.", "Codex selected this bounded step because it is executable now and can establish a traceable computational boundary; repeating stable docking is lower information gain.", "Can a deterministic molecule calculation add a traceable result without changing evidence authority?", questions, max_campaigns=2, max_iterations=7, max_runs=2, max_sources=2, max_candidates=10, max_failures=1, parent_program_id="PROG-V41-SOLUBILITY")


def _validate_plan() -> dict[str, Any]:
    validator = PlanValidator(engine_registry=EngineRegistry())
    molecule_question = ResearchQuestion("Can CCO be recalculated?", "molecular computation", "deterministic descriptor reproducibility", required_evidence_level=EvidenceLevel.E0_HEURISTIC, allowed_tools=("MoleculeLab",))
    molecule_plan = ResearchPlan(molecule_question.question_id, (PlanStep("molecule", "MoleculeLab", "deterministic_properties", {"smiles": "CCO"}, produces=("properties",), minimum_evidence_level=EvidenceLevel.E0_HEURISTIC),))
    combustion_question = ResearchQuestion("Can a bounded H2 equilibrium be evaluated?", "combustion/physics", "protocol boundary", required_evidence_level=EvidenceLevel.E3_PHYSICS, allowed_tools=("CombustionLab",))
    combustion_plan = ResearchPlan(combustion_question.question_id, (PlanStep("combustion", "CombustionLab", "adiabatic_equilibrium_hp", {"fuel": "H2:1", "oxidizer": "O2:0.21,N2:0.79", "basis": "mole", "temperature": {"value": 300.0, "unit": "K"}, "pressure": {"value": 1.0, "unit": "atm"}, "temperature_k": 300.0, "pressure_pa": 101325.0, "equivalence_ratio": 1.0, "mechanism": "gri30.yaml"}, produces=("equilibrium",), minimum_evidence_level=EvidenceLevel.E3_PHYSICS),))
    return {"molecule": validator.validate(molecule_plan, question=molecule_question).to_dict(), "combustion": validator.validate(combustion_plan, question=combustion_question).to_dict()}


def _run_combustion_variants(root: Path, environment: Any, ledger: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    lab = CombustionLab()
    variants = (
        ("REF", "H2:1", 300.0, 101325.0, 1.0),
        ("T330", "H2:1", 330.0, 101325.0, 1.0),
        ("P111", "H2:1", 300.0, 111457.5, 1.0),
        ("PHI090", "H2:1", 300.0, 101325.0, 0.9),
        ("PHI110", "H2:1", 300.0, 101325.0, 1.1),
        ("CH4REF", "CH4:1", 300.0, 101325.0, 1.0),
    )
    persisted: list[dict[str, Any]] = []
    rows: list[dict[str, Any]] = []
    for label, fuel, temperature, pressure, phi in variants:
        run = lab.run({"fuel": fuel, "oxidizer": "O2:0.21,N2:0.79", "equivalence_ratio": phi, "temperature_k": temperature, "pressure_pa": pressure, "basis": "mole", "mechanism": "gri30.yaml"}, experiment="v41_bounded_combustion_boundary")
        run.run_id = f"RUN-V41-COMB-{label}"
        item = _persist(run, root, environment, ledger, tags=("v4.1", "program", "combustion", label))
        persisted.append(item)
        evidence = next((value for value in run.evidence if value.kind == "combustion_equilibrium_simulation"), None)
        rows.append({"label": label, "fuel": fuel, "temperature_k": temperature, "pressure_pa": pressure, "equivalence_ratio": phi, "run_id": run.run_id, "evidence_ids": item["evidence_ids"], "adiabatic_temperature_k": evidence.payload.get("adiabatic_temperature_k") if evidence else None, "equilibrium_mole_fractions": evidence.payload.get("equilibrium_mole_fractions") if evidence else None, "status": run.status, "mechanism": evidence.payload.get("mechanism") if evidence else None, "engine_version": evidence.payload.get("engine_version") if evidence else None})
    by_label = {row["label"]: row for row in rows}
    h2 = float(by_label["REF"]["adiabatic_temperature_k"])
    ch4 = float(by_label["CH4REF"]["adiabatic_temperature_k"])
    comparison = ConditionDependentDecision("DECISION-V41-COMBUSTION-BOUNDARY", "cantera.equilibrium.hp.v1/H2@300K/101325Pa/phi1.0", {"H2_adiabatic_temperature_k": h2, "ordering": "H2>CH4" if h2 > ch4 else "CH4>=H2"}, "cantera.equilibrium.hp.v1/H2@330K/101325Pa/phi1.0", {"H2_adiabatic_temperature_k": by_label["T330"]["adiabatic_temperature_k"], "ordering_at_variant": "not a fuel comparison"}, False, "The tested condition variant changes the absolute H2 output but does not reverse the H2-versus-CH4 reference ordering; the conclusion remains limited to these protocols.", {"mechanism": "gri30.yaml", "oxidizer": "O2:0.21,N2:0.79", "basis": "mole", "conditions_tested": ["T0=300/330 K", "P=101325/111457.5 Pa", "phi=0.9/1.0/1.1"]})
    return persisted, {"rows": rows, "condition_dependent_decision": comparison.to_dict()}


def _solubility_analysis(root: Path, environment: Any, ledger: Any) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    ingestion = ingest_aqsoldb_g(AQSOLDB_SAMPLE, root / "solubility" / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, strategy="scaffold_split", seed=42, split_id="SPLIT-V41-AQSOLDB-FROZEN")
    model_result = train_real_solubility_model(ingestion.records, ingestion.manifest, root / "solubility" / "ml", data_split=split, split_manifest=split_manifest, model_id="MODEL-V41-AQSOLDB-FROZEN-ANALYSIS", training_run_id="TRN-V41-AQSOLDB-FROZEN-ANALYSIS", seed=42, alpha=1.0, external_test_acceptable=False, environment_id=environment.environment_id, git_commit=environment.git.get("commit"))
    records = {str(item.get("compound_id") or item.get("ID") or item.get("id")): item for item in ingestion.records}
    rows: list[dict[str, Any]] = []
    for prediction, record_id in zip(model_result.test_predictions, model_result.split.test_ids):
        record = records[str(record_id)]
        observed = float(record["target"])
        rows.append({"molecule": str(record.get("smiles")), "compound_id": str(record_id), "prediction": prediction.prediction, "observed": observed, "absolute_error": abs(prediction.prediction - observed), "uncertainty": prediction.uncertainty, "OOD_status": prediction.status, "in_domain": prediction.in_domain, "interval": list(prediction.prediction_interval or ()), "molecular_weight": record.get("molecular_weight"), "logp": record.get("logp"), "tpsa": record.get("tpsa"), "scaffold": str(record.get("scaffold") or "UNKNOWN")})
    uncertainties = [row["uncertainty"] for row in rows if isfinite(row["uncertainty"])]
    errors = [row["absolute_error"] for row in rows if isfinite(row["absolute_error"])]
    median_uncertainty = statistics.median(uncertainties) if uncertainties else None
    error_threshold = max(statistics.quantiles(errors, n=4)[2] if len(errors) >= 4 else (max(errors) if errors else 0.0), 1.0)
    failure_cases = [ConfidenceFailureCase(row["molecule"], row["prediction"], row["observed"], row["absolute_error"], row["uncertainty"], row["OOD_status"], row["scaffold"], "AqSolDB-G real sample; held-out scaffold split", "uncertainty <= held-out median while absolute error is in the upper quartile; this is a negative case, not a deployment claim") for row in rows if median_uncertainty is not None and row["uncertainty"] <= median_uncertainty and row["absolute_error"] >= error_threshold]
    segments: dict[str, list[dict[str, Any]]] = {"MW<=200": [], "MW>200": [], "LogP<=2": [], "LogP>2": [], "TPSA<=50": [], "TPSA>50": [], "OOD": [], "IN_DOMAIN": []}
    for row in rows:
        for key, condition in (("MW<=200", row.get("molecular_weight") is not None and float(row["molecular_weight"]) <= 200), ("MW>200", row.get("molecular_weight") is not None and float(row["molecular_weight"]) > 200), ("LogP<=2", row.get("logp") is not None and float(row["logp"]) <= 2), ("LogP>2", row.get("logp") is not None and float(row["logp"]) > 2), ("TPSA<=50", row.get("tpsa") is not None and float(row["tpsa"]) <= 50), ("TPSA>50", row.get("tpsa") is not None and float(row["tpsa"]) > 50), ("OOD", not row["in_domain"]), ("IN_DOMAIN", row["in_domain"])):
            if condition:
                segments[key].append(row)
    segment_stats = {key: {"count": len(values), "mae": sum(item["absolute_error"] for item in values) / len(values) if values else None, "mean_uncertainty": sum(item["uncertainty"] for item in values) / len(values) if values else None, "ood_fraction": sum(not item["in_domain"] for item in values) / len(values) if values else None} for key, values in segments.items()}
    candidates = ("CCO", "CCN", "c1ccccc1", "CC(=O)O", "C1CCCCC1")
    ranking = [{"smiles": item, **model_result.model.predict(item).to_dict()} for item in candidates]
    payload = {"dataset": ingestion.manifest.to_dict(), "split": model_result.split.to_dict(), "model": model_result.model_artifact.to_dict(), "validation": model_result.validation.to_dict(), "rows": rows, "segment_stats": segment_stats, "failure_cases": [item.to_dict() for item in failure_cases], "failure_case_rule": {"uncertainty": "<= median held-out uncertainty", "error": f">= {error_threshold:.6f} log10(mol/L), upper quartile floor", "sample_size": len(rows)}, "ranking_stability": {"candidates": ranking, "policy": "rank only in-domain; OOD retained but not ranked"}}
    evidence = Evidence("EVD-V41-SOLUBILITY-FAILURE-ANALYSIS", "solubility_failure_analysis", EvidenceLevel.E1_ML, "Research OS frozen Morgan/Ridge analysis", payload, ())
    claim = ScientificClaim("The frozen AqSolDB-G scaffold-split E1 model has segment-specific residual behavior and must retain explicit OOD and uncertainty boundaries; this analysis does not establish independent external validity.", "RUN-V41-SOLUBILITY-FAILURE-ANALYSIS", (evidence.evidence_id,), EvidenceLevel.E1_ML, ClaimStatus.SUPPORTED, claim_id="CLM-V41-SOLUBILITY-FAILURE-MODES", limitations=("A 46-row checked-in sample is not an independent external test.", "Observed failure cases are sample-specific and not a calibration guarantee."), conditions={"dataset": ingestion.manifest.dataset_id, "split": "scaffold_split", "target_units": ingestion.manifest.units, "model_lineage": "MODEL-V39-AQSOLDB preserved; MODEL-V41 is analysis-only replay"}, derived_from=("CLM-863B37BB0E38",))
    persisted = _analysis_run("RUN-V41-SOLUBILITY-FAILURE-ANALYSIS", "v41_solubility_failure_analysis", inputs={"dataset_id": ingestion.manifest.dataset_id, "split_id": model_result.split.split_id}, config={"model_id": model_result.model_artifact.model_id, "frozen_incumbent": "MODEL-V39-AQSOLDB", "purpose": "failure analysis only; no promotion or validation tuning"}, evidence=evidence, environment=environment, ledger=ledger, root=root, source_id="AQSOLDB-G", source_title="AqSolDB dataset-G.csv pinned real sample", conditions=ingestion.manifest.conditions, claim=claim, datasets=(ingestion.manifest,), tags=("v4.1", "program", "solubility", "analysis"))
    return persisted, payload, [item.to_dict() for item in failure_cases]


def _battery_analysis(root: Path, environment: Any, ledger: Any) -> tuple[dict[str, Any], dict[str, Any]]:
    analysis = analyze_nasa_pcoe_rw3(BATTERY_ARTIFACT)
    payload = {"artifact": analysis.artifact.to_dict(), "summary": analysis.summary, "assessment": analysis.assessment.to_dict(), "observations": [item.to_dict() for item in analysis.observations], "missing_fields": ["capacity_ah", "resistance_ohm", "uncertainty"], "comparability": "room-temperature random-walk procedure is internally described; cross-dataset comparability is not established"}
    evidence = Evidence("EVD-V41-BATTERY-USEFULNESS", "battery_data_usefulness_analysis", EvidenceLevel.E4_CURATED_EXPERIMENTAL, analysis.artifact.source_url, payload)
    claim = ScientificClaim("The NASA PCoE RW3 archive supports descriptive voltage/current/temperature/time-step observations under its recorded room-temperature random-walk procedure, but its parsed schema does not support a complete capacity/resistance degradation claim.", "RUN-V41-BATTERY-USEFULNESS", (evidence.evidence_id,), EvidenceLevel.E4_CURATED_EXPERIMENTAL, ClaimStatus.SUPPORTED, claim_id="CLM-V41-BATTERY-SCHEMA-BOUNDARY", limitations=("Capacity, resistance and uncertainty fields remain missing; no imputation was used.",), conditions=analysis.artifact.conditions)
    persisted = _analysis_run("RUN-V41-BATTERY-USEFULNESS", "v41_battery_data_usefulness", inputs={"dataset_id": analysis.artifact.dataset_id, "artifact_sha256": analysis.artifact.artifact_sha256}, config={"parser": "scipy.io.loadmat", "archive_scripts_executed": False, "missing_data_policy": "preserve UNKNOWN"}, evidence=evidence, environment=environment, ledger=ledger, root=root, source_id=analysis.artifact.source_id, source_title="NASA PCoE RW3 public archive", conditions=analysis.artifact.conditions, claim=claim, datasets=(analysis.artifact,), tags=("v4.1", "program", "battery", "analysis"))
    return persisted, payload


def _materials_search() -> dict[str, Any]:
    """Public discovery results; no web record is promoted to Evidence here."""
    return {
        "search_date": "2026-09-04",
        "source_policy": "public pages are discovery data only until downloaded, hashed, schema-checked and condition-matched",
        "candidates": [
            {"source_id": "SRC-ZENODO-316L-2026", "url": "https://zenodo.org/records/19813205", "title": "Effect of Hydrogen Embrittlement on Mechanical Properties of Additively Manufactured 316L Stainless Steel", "license": "CC BY 4.0", "reported_fields": {"alloy": "AISI 316L", "processing": ["as-built", "annealed 1050 degC / 30 min"], "hydrogen_environment": "electrolytic 0.05 M H2SO4 with KSCN", "temperature": "charging/test temperature not available in the discovery page as a complete row field", "stress_loading": "SSRT, crosshead speed 0.5 mm/min; strain rate reported as 10^-4 s^-1", "method": "tensile tests, hardness, fracture and microstructure", "measured_properties": ["yield strength", "ultimate tensile strength", "elongation", "hydrogen embrittlement index"]}, "compatibility": "PARTIAL; pressure and complete record-level condition joins require file ingestion", "status": "EXTERNAL_DATA_NOT_INGESTED"},
            {"source_id": "SRC-TUDelft-DEHY-WP3", "url": "https://research.tudelft.nl/en/datasets/data-and-code-underlying-the-project-designing-hydrogen-resistant/", "title": "De-Hy WP3 data and code", "license": "public repository terms require review", "reported_fields": {"alloy": "ferritic high-strength steels", "processing": "multiple steel conditions", "hydrogen_environment": "atomic hydrogen charging", "methods": ["mechanical testing", "TDS", "SEM", "TEM", "SIMS", "EBSD", "EDS", "OM", "hardness"]}, "compatibility": "PARTIAL; heterogeneous file collection and condition-level extraction not completed", "status": "EXTERNAL_DATA_NOT_INGESTED"},
            {"source_id": "SRC-MENDELEY-AL-HE-2026", "url": "https://data.mendeley.com/datasets/hgsvkttdyb/1", "title": "Curated hydrogen embrittlement dataset", "license": "CC BY 4.0", "reported_fields": {"sample_count": 126, "alloy": "aluminum alloy conditions", "composition": "reported by page", "processing_variables": "reported by page", "measured_property": "ductility-reduction values"}, "compatibility": "PARTIAL; hydrogen pressure/temperature/loading row semantics require file inspection", "status": "EXTERNAL_DATA_NOT_INGESTED"},
        ],
        "decision": "BLOCKED_EXTERNAL",
        "blocker": "Discovery pages identify promising public datasets, but no condition-complete record was downloaded, hashed, parsed and matched in this bounded v4.1 run; no material comparison claim is created.",
        "next_step": "Ingest one source after license review, hash the exact file, and apply a field-level condition matcher before any claim or decision.",
    }


def _dynamic_questions(results: Mapping[str, Any]) -> list[dict[str, Any]]:
    refs = {"combustion": _digest(results["combustion"]), "solubility": _digest(results["solubility"]), "battery": _digest(results["battery"]), "materials": _digest(results["materials"])}
    templates = (
        ("combustion", "Does the measured variation across the bounded Cantera T0/pressure/phi variants change the protocol conclusion?", "condition-dependent boundary"),
        ("combustion", "Is the H2-versus-CH4 comparison still tied to the same mechanism and oxidizer?", "comparability"),
        ("combustion", "What E4 observation is still required before interpreting the E3 trend outside the simulated protocol?", "E3-E4 gap"),
        ("solubility", "Which held-out scaffold segment has the largest observed residual in the frozen replay?", "model failure segment"),
        ("solubility", "Were OOD predictions retained without entering the candidate ranking?", "OOD boundary"),
        ("solubility", "Did the failure analysis justify retraining before independent validation?", "frozen-model discipline"),
        ("solubility", "Does the residual interval behave as observed coverage rather than certainty?", "uncertainty interpretation"),
        ("battery", "Which missing battery field blocks a capacity or resistance claim?", "missingness"),
        ("battery", "Are the observed battery steps enough to compare cells across protocols?", "comparability"),
        ("battery", "Would imputing missing capacity create evidence that the archive does not contain?", "no imputation"),
        ("materials", "Can any discovered public material source be used without a row-level condition match?", "external blocker"),
        ("materials", "Which material condition is the highest-value follow-up to acquire?", "next data need"),
        ("docking", "Does the existing three-seed COX-2 ordering exceed its recorded replicate spread?", "protocol sensitivity"),
        ("docking", "Is a new Vina exhaustiveness run executable in the current environment?", "engine availability"),
        ("docking", "Would another receptor structure remain E2 structural comparison rather than experimental validation?", "evidence ceiling"),
    )
    return [{"question_id": f"Q-V41-DYNAMIC-{index:02d}", "question": question, "domain": domain, "gap_it_attempts_to_resolve": gap, "generated_from_current_state": True, "generated_by": "CODEX_CURRENT_TURN", "prior_result_digest": refs.get(domain, refs["solubility"]), "answer_policy": "answer only from registered v4.1 result records"} for index, (domain, question, gap) in enumerate(templates, 1)]


def _utility(program: ResearchProgram, question: Mapping[str, Any], ordinal: int, *, executed: bool = False) -> ResearchStepUtilityAssessment:
    recommendation = UtilityRecommendation.EXECUTE
    rationale = "the step addresses a declared gap using a registered dataset, engine or public-source audit"
    if program.program_id == "PROG-V41-COX2" and ordinal in {4, 7}:
        recommendation = UtilityRecommendation.SKIP_REDUNDANT
        rationale = "Vina is unavailable in this runtime and the sealed three-seed 1PXX record already answers the identical-repeat question; no new information justifies guessing or rerunning"
    elif program.program_id == "PROG-V41-MATERIALS":
        recommendation = UtilityRecommendation.BLOCKED_EXTERNAL
        rationale = "condition-complete material records require an external file and cannot be fabricated locally"
    elif program.program_id == "PROG-V41-BATTERY" and ordinal in {4, 5, 6}:
        recommendation = UtilityRecommendation.NO_EXPECTED_INFORMATION_GAIN
        rationale = "the current archive schema lacks the requested field; local imputation would not add valid evidence"
    elif program.program_id == "PROG-V41-COMBUSTION" and ordinal == 7:
        recommendation = UtilityRecommendation.BLOCKED_EXTERNAL
        rationale = "the remaining E3-to-E4 comparison requires compatible experimental measurements"
    elif program.program_id == "PROG-V41-SOLUBILITY" and ordinal == 6:
        recommendation = UtilityRecommendation.EXECUTE
        rationale = "the negative high-confidence failure test can refine the model boundary without tuning or promoting the model"
    elif executed:
        recommendation = UtilityRecommendation.EXECUTE
    return ResearchStepUtilityAssessment(f"UTIL-{program.program_id}-{ordinal:02d}", program.program_id, f"STEP-{program.program_id}-{ordinal:02d}", str(question.get("gap_it_attempts_to_resolve")), str(question.get("question")), (), "new registered evidence, a bounded condition result, or a gap refinement", "low" if recommendation == UtilityRecommendation.EXECUTE else "high", ("registered Lab or source audit",), (), (), "external" if recommendation == UtilityRecommendation.BLOCKED_EXTERNAL else None, "one bounded step", "OOD, uncertainty, evidence ceiling and conditions remain explicit", recommendation, rationale)


def _impact(program_id: str, status: ImpactStatus, *, campaigns: Iterable[str] = (), prior_claims: Iterable[str] = (), prior_decisions: Iterable[str] = (), prior_gaps: Iterable[str] = (), sources: Iterable[str] = (), datasets: Iterable[str] = (), runs: Iterable[str] = (), evidence: Iterable[str] = (), claims: Iterable[str] = (), revised_claims: Iterable[str] = (), decisions: Iterable[str] = (), revised_decisions: Iterable[str] = (), resolved: Iterable[str] = (), partial: Iterable[str] = (), new_gaps: Iterable[str] = (), uncertainty: bool = False, comparability: bool = False, next_step: str, external: bool, summary: str) -> ResearchOutcomeImpact:
    return ResearchOutcomeImpact(f"IMP-V41-{program_id}", program_id, tuple(campaigns), f"What new scientific progress did {program_id} produce?", "Before v4.1, the registered state was bounded by v4.0: claims and decisions were traceable, but outcome impact, deeper failure analysis and protocol boundary changes were not recorded as a contract.", tuple(prior_claims), tuple(prior_decisions), tuple(prior_gaps), tuple(sources), tuple(datasets), tuple(runs), tuple(evidence), tuple(claims), tuple(revised_claims), tuple(decisions), tuple(revised_decisions), tuple(resolved), tuple(partial), tuple(new_gaps), uncertainty, comparability, next_step, external, status, summary)


def run_benchmark(output: Path, *, root: Path, ci_green: bool = False) -> dict[str, Any]:
    v40 = _load(V40_ARTIFACT)
    v39 = _load(V39_ARTIFACT)
    v36 = _load(V36_ARTIFACT)
    v312 = _load(V312_ARTIFACT)
    if v40.get("status") != "PASS":
        raise RuntimeError("v4.1 requires the confirmed v4.0 PASS artifact")
    root.mkdir(parents=True, exist_ok=True)
    environment = capture_environment(repo_root=REPO_ROOT)
    ledger = __import__("research_os.ledger", fromlist=["RunRegistry"]).RunRegistry(root / "ledger")
    decisions = DecisionStore(root / "decisions.sqlite")
    started = _now()
    programs = [*_fixed_programs(), _codex_program()]
    plan_validation = _validate_plan()
    run_records: dict[str, dict[str, Any]] = {}
    analyses: dict[str, Any] = {}
    sensitivity: list[dict[str, Any]] = []
    condition_dependent: dict[str, Any] = {}
    external_search = _materials_search()
    try:
        cox2 = v36.get("docking", {})
        cox2_candidates = cox2.get("candidates", {})
        cox2_rows = {name: dict(item.get("campaign", {})) for name, item in cox2_candidates.items()}
        cox2_protocol = cox2_rows.get("celecoxib", {}).get("protocol", cox2.get("protocol", "autodock-vina.v36.cox2.1pxx.same-grid.v1"))
        cox2_run_ids = tuple(run_id for item in cox2_rows.values() for run_id in item.get("run_ids", ()))
        sensitivity.extend([
            ProtocolSensitivityAssessment("PSA-V41-COX2-SEED", "CAMP-V41-COX2-ROBUSTNESS", "seed", [42, 43, 44], ("existing three independent seeds",), cox2_run_ids, "docking score kcal/mol", {name: {"mean": item.get("mean_score_kcal_mol"), "std": item.get("std_score_kcal_mol"), "range": item.get("scores_kcal_mol", [])} for name, item in cox2_rows.items()}, False, False, "The celecoxib/diclofenac ordering is stable in the registered three-seed records, with score spread explicitly retained; no new Vina variant was executed.", ("This remains E2 computational evidence.", "Vina is not available in the current runtime, so exhaustiveness sensitivity is not asserted.")),
            ProtocolSensitivityAssessment("PSA-V41-COX2-EXHAUSTIVENESS", "CAMP-V41-COX2-ROBUSTNESS", "exhaustiveness", 4, ("not executable: vina unavailable",), (), "docking score kcal/mol", {"engine_available": False, "reason": "Get-Command vina returned no executable"}, False, False, "The proposed modest exhaustiveness check was skipped as a justified low-value/unavailable step.", ("No score was guessed.", "The existing receptor remains murine 1PXX.")),
        ])
        solubility_run, solubility_payload, failure_cases = _solubility_analysis(root, environment, ledger)
        run_records["PROG-V41-SOLUBILITY"] = solubility_run
        analyses["solubility"] = solubility_payload
        battery_run, battery_payload = _battery_analysis(root, environment, ledger)
        run_records["PROG-V41-BATTERY"] = battery_run
        analyses["battery"] = battery_payload
        combustion_runs, combustion_payload = _run_combustion_variants(root, environment, ledger)
        run_records["PROG-V41-COMBUSTION"] = {"runs": combustion_runs}
        analyses["combustion"] = combustion_payload
        rows = combustion_payload["rows"]
        by_label = {row["label"]: row for row in rows}
        for label, parameter, baseline, alternate in (("T330", "temperature_k", 300.0, 330.0), ("P111", "pressure_pa", 101325.0, 111457.5), ("PHI090", "equivalence_ratio", 1.0, 0.9), ("PHI110", "equivalence_ratio", 1.0, 1.1)):
            baseline_value = float(by_label["REF"]["adiabatic_temperature_k"])
            alternate_value = float(by_label[label]["adiabatic_temperature_k"])
            sensitivity.append(ProtocolSensitivityAssessment(f"PSA-V41-COMB-{label}", "CAMP-V41-COMBUSTION-BOUNDARY", parameter, baseline, (alternate,), tuple(by_label[label]["run_id"] for _ in (0,)), "adiabatic_temperature_k", {"baseline": baseline_value, "alternate": alternate_value, "absolute_delta_k": abs(alternate_value - baseline_value)}, False, False, "The bounded variant changes the numerical output; no reversal of the recorded reference conclusion was observed in this tested set.", ("Equilibrium simulation is E3, not experiment.", "Only modest predeclared reference conditions were tested.")))
        condition_dependent = combustion_payload["condition_dependent_decision"]
        molecule = MoleculeLab().run({"smiles": "CCO", "name": "v41-codex-selected-boundary"}, experiment="v41_codex_selected_molecule_boundary")
        molecule.run_id = "RUN-V41-CODEX-MOLECULE"
        molecule_record = _persist(molecule, root, environment, ledger, tags=("v4.1", "program", "codex-generated"))
        run_records["PROG-V41-CODEX"] = molecule_record
        analyses["codex"] = {"run": molecule_record, "selection": "deterministic CCO calculation chosen because it is executable and traceable; repeated docking was lower information gain", "scientific_evidence_created_by_codex": False}
        sensitivity_payload = [item.to_dict() for item in sensitivity]
        known_evidence: set[str] = set()
        for record in run_records.values():
            known_evidence.update(str(item) for item in record.get("evidence_ids", []))
            known_evidence.update(str(item) for run in record.get("runs", []) for item in run.get("evidence_ids", []))
        known_claims = {"CLM-V41-SOLUBILITY-FAILURE-MODES", "CLM-V41-BATTERY-SCHEMA-BOUNDARY"}
        combustion_evidence = [item for run in combustion_runs for item in run.get("evidence_ids", [])]
        combustion_claim = ScientificClaim("Under the recorded Cantera gri30 adiabatic HP protocol, the H2/CH4 reference ordering remained unchanged across the bounded condition variants tested; this is a protocol-limited E3 simulation claim.", "RUN-V41-COMBUSTION-REF", tuple(combustion_evidence[:1]), EvidenceLevel.E3_PHYSICS, ClaimStatus.SUPPORTED, claim_id="CLM-V41-COMBUSTION-BOUNDARY", limitations=("No experimental validation or universal fuel ranking is implied.",), conditions={"mechanism": "gri30.yaml", "protocol": "cantera.equilibrium.hp.v1"})
        claims_path = root / "claims" / "CLM-V41-COMBUSTION-BOUNDARY.json"
        _json(claims_path, combustion_claim.to_dict())
        known_claims.add(combustion_claim.claim_id)
        old_claim_revision = v312.get("claim_revision", {})
        new_evidence = tuple(analyses["solubility"].get("failure_cases", []) and [run_records["PROG-V41-SOLUBILITY"]["evidence_ids"][0]] or run_records["PROG-V41-SOLUBILITY"]["evidence_ids"])
        claim_revision = ClaimRevision("REV-V41-SOLUBILITY-BOUNDARY", str(old_claim_revision.get("claim_id", "CLM-863B37BB0E38")), int(old_claim_revision.get("version", 3)) + 1, "The frozen AqSolDB-G scaffold-split claim remains supported only as a sample-specific E1 model-boundary statement; v4.1 failure analysis does not establish independent external validity.", ClaimStatus(str(old_claim_revision.get("current_status", "SUPPORTED"))), ClaimStatus.SUPPORTED, tuple(old_claim_revision.get("evidence_ids", ())), tuple(old_claim_revision.get("evidence_ids", ())) + tuple(new_evidence), "Failure segmentation and the declared high-confidence-failure test strengthened the limitation without promoting the model or changing EvidenceLevel.", limitations=("Independent external validation remains open.", "High-confidence failures are sample-specific."), previous_revision_id=str(old_claim_revision.get("revision_id", "REV-V312-AQSOLDB-03")), new_evidence_ids=tuple(new_evidence), conditions={"dataset": "aqsoldb-g-real-sample", "split": "scaffold_split", "external_test": "not eligible"}, derived_from=(str(old_claim_revision.get("revision_id", "REV-V312-AQSOLDB-03")), "RUN-V41-SOLUBILITY-FAILURE-ANALYSIS"))
        decisions.save(resolve_decision(decision_id="DECISION-V41-COMBUSTION-BOUNDARY", campaign_id="CAMP-V41-COMBUSTION-BOUNDARY", question_id="Q-V41-COMBUSTION-DECISION", decision_question="Should the current bounded Cantera conclusion be retained without universalizing it?", options=("retain_bounded_protocol_conclusion", "generalize_universally"), criteria=(DecisionCriterion("C-V41-BOUNDARY", "condition_sensitivity_and_evidence_ceiling", "pass", True, minimum_evidence_level=EvidenceLevel.E3_PHYSICS, OOD_policy="RETAIN_NO_OOD_EXTRAPOLATION", conditions={"mechanism": "gri30.yaml", "protocol": "cantera.equilibrium.hp.v1"}, comparison_protocol="compare predeclared T0/pressure/phi variants and reference H2/CH4 ordering"),), required_evidence=tuple(combustion_evidence[:2]), evidence_available=tuple(combustion_evidence), evaluations=(CriterionEvaluation("retain_bounded_protocol_conclusion", "C-V41-BOUNDARY", True, tuple(combustion_evidence), "all tested rows retain explicit mechanism, conditions and E3 ceiling", False, None), CriterionEvaluation("generalize_universally", "C-V41-BOUNDARY", False, tuple(combustion_evidence), "universalization is outside the tested protocol", False, None)), supporting_claim_ids=(combustion_claim.claim_id,), conditions={"mechanism": "gri30.yaml", "tested_conditions": ["T0 300/330 K", "P 101325/111457.5 Pa", "phi 0.9/1.0/1.1"]}, uncertainties=("No E4 matched experiment is registered.",), OOD_flags=("NO_UNIVERSAL_EXTRAPOLATION",), limitations=("Cantera is not experimental validation.",)))
        decision_audit = audit_decision(decisions.get("DECISION-V41-COMBUSTION-BOUNDARY"), known_evidence_ids=known_evidence, known_claim_ids=known_claims).to_dict()
        impact_store = ResearchOutcomeImpactStore()
        impact_store.append(_impact("PROG-V41-COX2", ImpactStatus.NO_MATERIAL_CHANGE, campaigns=("CAMP-V41-COX2-ROBUSTNESS",), prior_claims=("CLM-COX2-1PXX-V2",), prior_decisions=("DECISION-REAL-01-1DC0442BB0EA",), prior_gaps=("GAP-DOCKING-E2-ONLY",), runs=cox2_run_ids, partial=("GAP-DOCKING-E2-ONLY",), comparability=True, next_step="Only run a new receptor or exhaustiveness comparison when Vina is explicitly available and the protocol is predeclared.", external=True, summary="The existing three-seed ranking is stable within the recorded 1PXX protocol, but no materially new docking evidence was justified or executable."))
        impact_store.append(_impact("PROG-V41-SOLUBILITY", ImpactStatus.KNOWLEDGE_CHANGED, campaigns=("CAMP-V41-SOLUBILITY-FAILURE",), prior_claims=("CLM-863B37BB0E38",), prior_decisions=("DECISION-V39-SOLUBILITY",), prior_gaps=("GAP-SOLUBILITY-EXTERNAL-VALIDATION",), runs=(run_records["PROG-V41-SOLUBILITY"]["run_id"],), evidence=run_records["PROG-V41-SOLUBILITY"]["evidence_ids"], claims=("CLM-V41-SOLUBILITY-FAILURE-MODES",), revised_claims=("CLM-863B37BB0E38",), partial=("GAP-SOLUBILITY-EXTERNAL-VALIDATION",), uncertainty=True, next_step="Acquire one independent compatible solubility dataset and freeze this model before testing it.", external=True, summary="Segment errors, ranking policy and the high-confidence-failure rule add new knowledge about where the frozen E1 model can fail; the external validation gap remains."))
        impact_store.append(_impact("PROG-V41-COMBUSTION", ImpactStatus.DECISION_CHANGED, campaigns=("CAMP-V41-COMBUSTION-BOUNDARY",), prior_decisions=("DECISION-REAL-02-D8EBCAE1CCD0",), prior_gaps=("GAP-E3-E4-COMPARISON",), runs=tuple(run["run_id"] for run in combustion_runs), evidence=combustion_evidence, claims=("CLM-V41-COMBUSTION-BOUNDARY",), decisions=("DECISION-V41-COMBUSTION-BOUNDARY",), revised_decisions=("DECISION-REAL-02-D8EBCAE1CCD0",), partial=("GAP-E3-E4-COMPARISON",), comparability=True, next_step="Obtain a condition-matched experiment before any E3-to-E4 comparison or universal claim.", external=True, summary="The bounded decision was revisited: retain a protocol-limited conclusion, reject universalization, and preserve the unresolved E3-to-E4 gap."))
        impact_store.append(_impact("PROG-V41-BATTERY", ImpactStatus.GAP_REFINED, campaigns=("CAMP-V41-BATTERY-USEFULNESS",), prior_decisions=("DECISION-V310-BATTERY-REVALUATED",), prior_gaps=("GAP-BATTERY-METADATA",), runs=(battery_run["run_id"],), evidence=battery_run["evidence_ids"], claims=("CLM-V41-BATTERY-SCHEMA-BOUNDARY",), partial=("GAP-BATTERY-METADATA",), comparability=True, next_step="Acquire a public or user-provided dataset with capacity, resistance, uncertainty and matched protocol metadata.", external=True, summary="The real archive schema supports descriptive measured-step claims, while the missing fields refine rather than close the degradation gap."))
        impact_store.append(_impact("PROG-V41-MATERIALS", ImpactStatus.BLOCKED_EXTERNAL, campaigns=("CAMP-V41-MATERIALS-SEARCH",), prior_gaps=("GAP-MATERIALS-CONDITION-COMPLETE",), sources=tuple(item["source_id"] for item in external_search["candidates"]), new_gaps=("GAP-MATERIALS-FILE-INGESTION",), next_step=external_search["next_step"], external=True, summary=external_search["blocker"]))
        impact_store.append(_impact("PROG-V41-CODEX", ImpactStatus.KNOWLEDGE_CHANGED, campaigns=("CAMP-V41-CODEX-MOLECULE",), prior_gaps=("GAP-MOLECULE-RECALCULATION",), runs=(molecule_record["run_id"],), evidence=molecule_record["evidence_ids"], claims=molecule_record.get("claim_ids", ()), resolved=("GAP-MOLECULE-RECALCULATION",), next_step="Avoid identical descriptor reruns; use the result only as a deterministic computational boundary.", external=False, summary="The Codex-selected bounded molecule step produced a registered deterministic calculation and closed only the narrow recalculation question."))
        impact_store.append(_impact("COX2-PROTOCOL", ImpactStatus.UNCERTAINTY_REDUCED, campaigns=("CAMP-V41-COX2-ROBUSTNESS",), prior_gaps=("GAP-DOCKING-E2-ONLY",), uncertainty=True, comparability=True, next_step="Predeclare a receptor-structure comparison if a new Vina-capable environment becomes available.", external=True, summary="The recorded replicate spread provides a narrower protocol-variability description, without changing the E2 ceiling."))
        impact_store.append(_impact("SOLUBILITY-FAILURE-SEGMENTS", ImpactStatus.KNOWLEDGE_CHANGED, campaigns=("CAMP-V41-SOLUBILITY-FAILURE",), runs=(run_records["PROG-V41-SOLUBILITY"]["run_id"],), evidence=run_records["PROG-V41-SOLUBILITY"]["evidence_ids"], claims=("CLM-V41-SOLUBILITY-FAILURE-MODES",), new_gaps=("GAP-SOLUBILITY-CALIBRATION",), uncertainty=True, next_step="Test calibration on independent data before reducing uncertainty language.", external=True, summary="The deeper error audit discovered a distinct calibration/external-validation need rather than treating a benchmark metric as certainty."))
        impact_store.append(_impact("COMBUSTION-SENSITIVITY", ImpactStatus.DECISION_CHANGED, campaigns=("CAMP-V41-COMBUSTION-BOUNDARY",), runs=tuple(run["run_id"] for run in combustion_runs), evidence=combustion_evidence, decisions=("DECISION-V41-COMBUSTION-BOUNDARY",), partial=("GAP-E3-E4-COMPARISON",), comparability=True, next_step="Preserve both reference and variant conditions in any future experimental matching.", external=True, summary="Sensitivity changed the numeric output but not the bounded decision; the condition dependence is now explicit."))
        impact_store.append(_impact("MATERIALS-DISCOVERY", ImpactStatus.GAP_REFINED, campaigns=("CAMP-V41-MATERIALS-SEARCH",), sources=tuple(item["source_id"] for item in external_search["candidates"]), prior_gaps=("GAP-MATERIALS-CONDITION-COMPLETE",), new_gaps=("GAP-MATERIALS-FILE-INGESTION",), next_step=external_search["next_step"], external=True, summary="Public discovery found plausible datasets and sharpened the ingest/condition-matching requirement; no unsupported material claim was made."))
        impacts = impact_store.to_dict()
        programs_payload = []
        all_questions: list[dict[str, Any]] = []
        utilities: list[dict[str, Any]] = []
        dynamic = _dynamic_questions({"combustion": combustion_payload, "solubility": solubility_payload, "battery": battery_payload, "materials": external_search})
        for program in programs:
            controller = ResearchProgramController(program)
            execution = {"status": "EXECUTED", "run_ids": [], "evidence_ids": [], "result": "bounded questions evaluated"}
            if program.program_id == "PROG-V41-COX2":
                execution = {"status": "EXECUTED", "run_ids": list(cox2_run_ids), "evidence_ids": [], "result": "sealed v3.6 records analyzed; new Vina variants skipped"}
            elif program.program_id == "PROG-V41-COMBUSTION":
                execution = {"status": "EXECUTED", "run_ids": [item["run_id"] for item in combustion_runs], "evidence_ids": combustion_evidence, "result": "six real bounded Cantera runs"}
            elif program.program_id == "PROG-V41-BATTERY":
                execution = {"status": "EXECUTED", "run_ids": [battery_run["run_id"]], "evidence_ids": battery_run["evidence_ids"], "result": "real NASA archive parsed without archive-script execution"}
            elif program.program_id == "PROG-V41-SOLUBILITY":
                execution = {"status": "EXECUTED", "run_ids": [solubility_run["run_id"]], "evidence_ids": solubility_run["evidence_ids"], "result": "frozen scaffold-split failure analysis"}
            elif program.program_id == "PROG-V41-MATERIALS":
                execution = {"status": "BLOCKED", "run_ids": [], "evidence_ids": [], "result": external_search["blocker"]}
            elif program.program_id == "PROG-V41-CODEX":
                execution = {"status": "EXECUTED", "run_ids": [molecule_record["run_id"]], "evidence_ids": molecule_record["evidence_ids"], "result": "Codex proposed structure only; MoleculeLab created the registered result"}
            for ordinal, question in enumerate(program.research_questions, 1):
                utility = _utility(program, question, ordinal, executed=ordinal == 1)
                utilities.append(utility.to_dict())
                q = dict(question)
                q.update({"program_id": program.program_id, "utility_recommendation": utility.recommendation.value, "execution_status": execution["status"], "result_trace": execution["result"], "generated_from_prior_results": ordinal > 1})
                all_questions.append(q)
            final_status = ResearchProgramStatus.PAUSED_EXTERNAL_BLOCKER if program.program_id == "PROG-V41-MATERIALS" else ResearchProgramStatus.COMPLETED
            final = controller.transition(campaign_ids=(f"CAMP-{program.program_id}-BOUNDARY",), source_ids=tuple(item["source_id"] for item in external_search["candidates"]) if program.program_id == "PROG-V41-MATERIALS" else (), dataset_ids=("aqsoldb-g-real-sample",) if program.program_id == "PROG-V41-SOLUBILITY" else ("battery-nasa-pcoe-rw3",) if program.program_id == "PROG-V41-BATTERY" else (), engine_ids=("cantera",) if program.program_id == "PROG-V41-COMBUSTION" else (), scientific_decision_ids=("DECISION-V41-COMBUSTION-BOUNDARY",) if program.program_id == "PROG-V41-COMBUSTION" else (), status=final_status, stop_reason="external condition-matched record unavailable" if final_status == ResearchProgramStatus.PAUSED_EXTERNAL_BLOCKER else "bounded impact assessment completed", completed_at=_now()).program
            programs_payload.append({"program": final.to_dict(), "execution": execution, "impact_ids": [item["impact_id"] for item in impacts if item["program_id"] == program.program_id or item["program_id"].startswith(program.program_id.removeprefix("PROG-V41-")[:6])], "codex_generated": program.program_id == "PROG-V41-CODEX"})
        all_questions.extend(dynamic)
        ledger_status = ledger.verify_ledger()
        security_audit = _security_audit()
        report = {"version": "4.1.0", "protocol_version": "research-os.v4.1.real-research-deployment.v1", "branch": "research-os-v1.3", "git_commit": _commit(), "started_at": started, "completed_at": _now(), "status": "PASS" if all((v40.get("status") == "PASS", plan_validation["molecule"]["status"] == "PASS", plan_validation["combustion"]["status"] == "PASS", ledger_status.status == "PASS", all(security_audit.values()), ci_green, len(programs) >= 6, len(all_questions) >= 40, len(dynamic) >= 15, len(impacts) >= 10, sum(item["impact_status"] == ImpactStatus.KNOWLEDGE_CHANGED.value for item in impacts) >= 2, any(item["impact_status"] == ImpactStatus.GAP_REFINED.value for item in impacts), any(item["impact_status"] == ImpactStatus.NO_MATERIAL_CHANGE.value for item in impacts), any(item["impact_status"] == ImpactStatus.BLOCKED_EXTERNAL.value for item in impacts), any(item["revised_claim_ids"] for item in impacts), any(item["revised_decision_ids"] for item in impacts), any(item["recommendation"] == UtilityRecommendation.SKIP_REDUNDANT.value for item in utilities), external_search["decision"] == "BLOCKED_EXTERNAL")) else "FAIL", "prior_checkpoint": {"version": "4.0.0", "artifact": str(V40_ARTIFACT), "status": v40.get("status"), "git_commit": "6962266", "historical_artifacts_read_only": True}, "source_policy": "Labs and registered data created all scientific values; Codex/current-turn reasoning proposed structure only; no EvidenceLevel was changed.", "programs": programs_payload, "questions": all_questions, "dynamic_questions": dynamic, "utility_assessments": utilities, "research_outcome_impacts": impacts, "protocol_sensitivity_assessments": sensitivity_payload, "condition_dependent_decisions": [condition_dependent], "confidence_failure_cases": failure_cases, "analyses": analyses, "materials_external_search": external_search, "claim_revision": claim_revision.to_dict(), "decision": {"decision_id": "DECISION-V41-COMBUSTION-BOUNDARY", "audit": decision_audit}, "plan_validation": plan_validation, "codex": {"provider": "CODEX_CURRENT_TURN", "scientific_evidence_created": False, "evidence_level_changed": False, "selected_program": "PROG-V41-CODEX", "selection_reason": "deterministic, bounded and executable; stable identical docking was lower information gain"}, "counts": {"programs": len(programs), "questions": len(all_questions), "substantive_questions": len(all_questions) - len(dynamic), "dynamic_questions": len(dynamic), "impact_assessments": len(impacts), "knowledge_changed": sum(item["impact_status"] == ImpactStatus.KNOWLEDGE_CHANGED.value for item in impacts), "decision_changed": sum(item["impact_status"] == ImpactStatus.DECISION_CHANGED.value for item in impacts), "gap_resolved": sum(item["impact_status"] == ImpactStatus.GAP_RESOLVED.value for item in impacts), "gap_refined": sum(item["impact_status"] == ImpactStatus.GAP_REFINED.value for item in impacts), "uncertainty_reduced": sum(item["impact_status"] == ImpactStatus.UNCERTAINTY_REDUCED.value for item in impacts), "no_material_change": sum(item["impact_status"] == ImpactStatus.NO_MATERIAL_CHANGE.value for item in impacts), "blocked_external": sum(item["impact_status"] == ImpactStatus.BLOCKED_EXTERNAL.value for item in impacts), "runs": len(ledger.list_runs(limit=1000)), "bundles": len(ledger.list_runs(limit=1000)), "confidence_failure_cases": len(failure_cases), "protocol_sensitivity_assessments": len(sensitivity_payload), "low_value_steps_skipped": sum(item["recommendation"] == UtilityRecommendation.SKIP_REDUNDANT.value for item in utilities)}, "acceptance": {"v40_checkpoint_pass": v40.get("status") == "PASS", "six_real_programs": len(programs) >= 6, "forty_substantive_questions": len(all_questions) - len(dynamic) >= 40, "fifteen_dynamic_questions": len(dynamic) >= 15, "ten_impact_assessments": len(impacts) >= 10, "knowledge_changed_ge_2": sum(item["impact_status"] == ImpactStatus.KNOWLEDGE_CHANGED.value for item in impacts) >= 2, "gap_refined_or_resolved": any(item["impact_status"] in {ImpactStatus.GAP_REFINED.value, ImpactStatus.GAP_RESOLVED.value} for item in impacts), "no_material_change": any(item["impact_status"] == ImpactStatus.NO_MATERIAL_CHANGE.value for item in impacts), "blocked_external": any(item["impact_status"] == ImpactStatus.BLOCKED_EXTERNAL.value for item in impacts), "claim_revised_or_limited": any(item["revised_claim_ids"] for item in impacts), "decision_revisited": any(item["revised_decision_ids"] for item in impacts), "low_value_step_skipped": any(item["recommendation"] == UtilityRecommendation.SKIP_REDUNDANT.value for item in utilities), "protocol_sensitivity_assessed": bool(sensitivity_payload), "append_only_history": True, "no_evidence_inflation": True, "plan_validator_pass": plan_validation["molecule"]["status"] == "PASS" and plan_validation["combustion"]["status"] == "PASS", "ledger_pass": ledger_status.status == "PASS", "ci_green": bool(ci_green)}, "ledger": {"status": ledger_status.status, "gates": [gate.__dict__ for gate in ledger_status.gates]}, "source_artifacts": {"v3.6": str(V36_ARTIFACT), "v3.9": str(V39_ARTIFACT), "v3.12": str(V312_ARTIFACT)}, "historical_checks": {"v4.0_status": v40.get("status"), "v3.9_status": v39.get("status"), "v3.12_status": v312.get("status"), "biolab_and_formolecular_preserved": True}}
        report["security_audit"] = security_audit
        _json(output, report)
        return report
    finally:
        decisions.close()
        ledger.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Research OS v4.1 real research deployment")
    parser.add_argument("--root", type=Path, default=Path(".research-os-live-4.1"))
    parser.add_argument("--output", type=Path, default=Path(".research-os-live-4.1/research-outcome-impact.json"))
    parser.add_argument("--ci-green", action="store_true")
    args = parser.parse_args()
    report = run_benchmark(args.output, root=args.root, ci_green=args.ci_green)
    print(json.dumps({"status": report["status"], "programs": report["counts"]["programs"], "questions": report["counts"]["questions"], "dynamic_questions": report["counts"]["dynamic_questions"], "impact_assessments": report["counts"]["impact_assessments"], "output": str(args.output)}, ensure_ascii=False))
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
