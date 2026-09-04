from __future__ import annotations

import json

import pytest

from research_os.bundles import BundleVerificationStatus, verify_bundle
from research_os.core.types import EvidenceLevel, GateResult, GateStatus, RunLifecycle, RunManifest, RunMutationError
from research_os.datasets import DatasetManifest, DatasetRegistry, DatasetSourceType, DatasetSchemaError, convert_csv_to_parquet, dataset_ground_truth_gate
from research_os.environment import DependencyInfo, EnvironmentManifest
from research_os.golden import run_deliberate_failure, run_golden_workflow
from research_os.knowledge import KnowledgeLab, MOC, MOCRegistry, ReviewStatus, moc_integrity_gate
from research_os.ml import run_ml_golden_path
from research_os.molecule import MoleculeLab
from research_os.reproducibility import ReproducibilityStatus, compare_runs, rerun


def test_environment_hash_is_order_stable_and_detects_version_change():
    first = EnvironmentManifest(python={"implementation": "CPython", "version": "3.12"}, dependencies={"numpy": DependencyInfo(True, "1")}, engines={"cantera": DependencyInfo(False, None)})
    second = EnvironmentManifest(python={"version": "3.12", "implementation": "CPython"}, dependencies={"numpy": DependencyInfo(True, "1")}, engines={"cantera": DependencyInfo(False, None)})
    changed = EnvironmentManifest(python={"version": "3.12", "implementation": "CPython"}, dependencies={"numpy": DependencyInfo(True, "2")}, engines={"cantera": DependencyInfo(False, None)})
    assert first.environment_hash == second.environment_hash
    assert first.environment_hash != changed.environment_hash
    assert first.valid and not EnvironmentManifest.from_mapping({**first.to_dict(), "environment_hash": "0" * 64}).valid


def test_run_lifecycle_seal_is_immutable():
    run = RunManifest(lab="FixtureLab", experiment="lifecycle", inputs={"x": 1})
    assert run.lifecycle == RunLifecycle.CREATED
    run.start()
    run.gates.append(GateResult("GATE-1", "RULE-1", GateStatus.PASS, "ok"))
    run.complete()
    assert run.lifecycle == RunLifecycle.COMPLETED
    run.seal()
    assert run.lifecycle == RunLifecycle.SEALED
    with pytest.raises(RunMutationError):
        run.inputs["x"] = 2
    with pytest.raises(RunMutationError):
        run.gates.append(GateResult("GATE-2", "RULE-2", GateStatus.PASS, "no"))
    with pytest.raises(RunMutationError):
        run.transition(RunLifecycle.RUNNING)


def test_rerun_creates_lineage_and_preserves_original():
    environment = EnvironmentManifest(git={"commit": "abc", "branch": "test", "dirty": False})
    original = MoleculeLab().run({"smiles": "CCO"})
    original.attach_environment(environment)
    original.seal()
    rerun_run = rerun(original, MoleculeLab(), environment=environment)
    assert rerun_run.run_id != original.run_id
    assert rerun_run.rerun_of == original.run_id
    assert original.rerun_of is None
    comparison = compare_runs(original, rerun_run)
    assert comparison.status == ReproducibilityStatus.REPRODUCED
    assert comparison.same_inputs and comparison.same_config and comparison.same_evidence_values


def test_dataset_persistence_csv_to_parquet_and_schema_validation(tmp_path):
    csv_path = tmp_path / "fixture.csv"
    csv_path.write_text("id,value\n1,alpha\n2,beta\n", encoding="utf-8")
    parquet_path = tmp_path / "curated" / "fixture.parquet"
    manifest = convert_csv_to_parquet(csv_path, parquet_path, dataset_id="fixture", version="1", schema_id="fixture-v1", transformation_run_id="RUN-CONVERT-1")
    assert manifest.row_count == 2 and manifest.column_count == 2 and manifest.source_file_hash
    registry = DatasetRegistry(root=tmp_path / "registry")
    registered = registry.register(manifest)
    loaded = DatasetRegistry(root=tmp_path / "registry").get("fixture", "1")
    assert loaded.sha256 == registered.sha256 and registry.verify_dataset("fixture", "1")
    bad = tmp_path / "bad.csv"
    bad.write_text("id,value\n1,alpha,extra\n", encoding="utf-8")
    with pytest.raises(DatasetSchemaError):
        convert_csv_to_parquet(bad, tmp_path / "bad.parquet", dataset_id="bad", version="1", schema_id="bad-v1")


def test_synthetic_dataset_cannot_be_experimental_ground_truth():
    manifest = DatasetManifest.from_records(dataset_id="synthetic", version="1", schema_id="s-v1", records=[{"x": 1}], source_types=(DatasetSourceType.TEST_SYNTHETIC,), synthetic_fraction=1.0, evidence_levels=(EvidenceLevel.TEST_SYNTHETIC,))
    assert manifest.is_synthetic and not manifest.is_experimental_ground_truth
    assert dataset_ground_truth_gate(manifest).status == GateStatus.INSUFFICIENT_EVIDENCE


def test_golden_bundle_verifies_and_tampering_fails(tmp_path):
    result = run_golden_workflow(tmp_path / "golden", mode="stub")
    assert result.plan_run.passed and result.claim.status.value == "SUPPORTED"
    assert result.verification.status == BundleVerificationStatus.PASS
    manifest_path = result.bundle.root + "/manifest.json"
    with open(manifest_path, "a", encoding="utf-8") as fh:
        fh.write("\n")
    assert verify_bundle(result.bundle.root).status == BundleVerificationStatus.FAIL


def test_deliberate_failure_keeps_first_loss_and_skips_descendants(tmp_path):
    result = run_deliberate_failure(tmp_path / "failure")
    assert not result.plan_run.passed
    assert result.plan_run.first_loss is not None
    assert result.plan_run.first_loss.first_loss is not None
    assert result.plan_run.first_loss.first_loss.rule_id == "COMB-ENGINE-001"
    assert result.plan_run.steps["combustion"].status == "INDETERMINATE"
    assert result.plan_run.steps["thermal"].status == "SKIPPED"
    assert result.plan_run.steps["propulsion"].status == "SKIPPED"
    assert result.verification.status == BundleVerificationStatus.PASS


def test_ml_golden_path_rejects_worse_candidate_without_reliability_percent():
    result = run_ml_golden_path()
    assert result.decision.promoted is False
    assert result.decision.first_loss is not None
    assert result.decision.first_loss.rule_id == "ML-PROMO-MAE-001"
    assert "reliability_percent" not in result.validation.metrics


def test_moc_and_knowledge_integrity_are_separate_from_evidence():
    moc = MOC("MOC-FUELS", "Fuels", "fuels", "Fixture navigation", zettel_ids=("ZTL-MISSING",), review_status=ReviewStatus.REVIEW_REQUIRED)
    gate = moc_integrity_gate(moc, known_zettel_ids=())
    assert gate.status == GateStatus.INDETERMINATE
    assert MOCRegistry().validate(moc, known_zettel_ids=()).rule_id == "KNOW-MOC-001"
    run = KnowledgeLab().run_moc({"moc_id": "MOC-FUELS", "title": "Fuels", "domain": "fuels", "description": "Fixture", "zettel_ids": ["ZTL-MISSING"]}, known_zettel_ids=set())
    assert run.first_loss is not None and run.first_loss.status == GateStatus.INDETERMINATE
