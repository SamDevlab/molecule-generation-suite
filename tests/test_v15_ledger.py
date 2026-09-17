from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.artifacts import ContentAddressedArtifactStore
from research_os.bundles import ResearchBundle, BundleVerificationStatus
from research_os.core.provenance import ProvenanceRecord, SourceType
from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunLineage, RunManifest
from research_os.environment import EnvironmentManifest
from research_os.golden import GoldenFixtureLab, run_deliberate_failure
from research_os.knowledge.claims import ClaimStatus, ScientificClaim
from research_os.ledger import LedgerConflictError, LedgerIntegrityError, LineageCycleError, RunDependency, RunRegistry
from research_os.orchestration import LabRegistry, PlanStep, ResearchOrchestrator, WorkflowPlan


def _run(run_id: str, value: int, *, lineage: RunLineage = RunLineage(), environment: EnvironmentManifest | None = None, model_id: str | None = None) -> RunManifest:
    run = RunManifest("FixtureLab", "ledger-test", {"value": value}, config={"seed": 42}, run_id=run_id, lineage=lineage)
    run.start()
    provenance = ProvenanceRecord(SourceType.COMPUTATION, "fixture-calculation", title="Fixture calculation")
    run.provenance.append(provenance)
    payload = {"value": value}
    if model_id:
        payload.update({"model_id": model_id, "training_run_id": "RUN-TRAINING"})
    evidence = Evidence(f"EVD-{run_id}", "fixture_result", EvidenceLevel.E2_COMPUTATIONAL, "fixture", payload, (provenance.provenance_id,))
    run.evidence.append(evidence)
    run.gates.append(GateResult(f"GATE-{run_id}", "FIXTURE-RULE-001", GateStatus.PASS, "fixture passed", (evidence.evidence_id,)))
    run.complete()
    if environment is not None:
        run.attach_environment(environment)
    run.seal()
    return run


def _bundle(root: Path, run: RunManifest, *, claim: ScientificClaim | None = None, artifact: Path | None = None, pack_artifacts: bool = False):
    return ResearchBundle.create(run, root, environment=run.environment_manifest, claims=(claim,) if claim else (), artifacts={"result.txt": artifact} if artifact else None, pack_artifacts=pack_artifacts)


def test_registration_is_idempotent_and_conflicts_are_explicit(tmp_path):
    env = EnvironmentManifest(python={"version": "test"}, git={"commit": "abc"})
    bundle = _bundle(tmp_path / "bundles", _run("RUN-IDEMPOTENT", 1, environment=env))
    registry = RunRegistry(tmp_path / "ledger")
    try:
        assert registry.register_run(bundle).status.value == "REGISTERED"
        assert registry.register_run(bundle).status.value == "ALREADY_REGISTERED"
        conflicting = _bundle(tmp_path / "other", _run("RUN-IDEMPOTENT", 2, environment=env))
        with pytest.raises(LedgerConflictError) as error:
            registry.register_run(conflicting)
        assert error.value.rule_id == "LEDGER-RUN-CONFLICT-001"
    finally:
        registry.close()


def test_register_transaction_rolls_back_on_broken_dependency(tmp_path):
    bundle = _bundle(tmp_path / "bundles", _run("RUN-ROLLBACK", 1, environment=EnvironmentManifest()))
    registry = RunRegistry(tmp_path / "ledger")
    try:
        with pytest.raises(LedgerIntegrityError):
            registry.register_run(bundle, dependencies=[("RUN-ROLLBACK", "RUN-MISSING", "depends_on")])
        assert registry.list_runs() == []
    finally:
        registry.close()


def test_search_is_typed_parameterized_and_paginates(tmp_path):
    manifest = _run("RUN-SEARCH", 1, environment=EnvironmentManifest())
    claim = ScientificClaim("value is recorded", manifest.run_id, (manifest.evidence[0].evidence_id,), EvidenceLevel.E2_COMPUTATIONAL, ClaimStatus.SUPPORTED)
    dataset = {"dataset_id": "fixture-dataset", "version": "1", "sha256": "a" * 64, "artifact_path": None}
    bundle = ResearchBundle.create(manifest, tmp_path / "bundles", environment=manifest.environment_manifest, dataset_manifests=(dataset,), claims=(claim,))
    registry = RunRegistry(tmp_path / "ledger")
    try:
        registry.register_run(bundle, tags=("golden",))
        assert registry.search_runs(lab="FixtureLab")[0].run_id == "RUN-SEARCH"
        assert registry.search_runs(lab="' OR 1=1 --") == []
        assert registry.search_runs(dataset_id="fixture-dataset", claim_id=claim.claim_id, tag="golden", limit=1)[0].run_id == "RUN-SEARCH"
        registry.save_query("golden", {"tag": "golden"})
        assert registry.run_saved_query("golden")[0].run_id == "RUN-SEARCH"
    finally:
        registry.close()


def test_rebuild_skips_invalid_fail_but_indexes_indeterminate(tmp_path):
    valid = _bundle(tmp_path / "bundles", _run("RUN-REBUILD", 1, environment=EnvironmentManifest()))
    broken = Path(valid.root) / "manifest.json"
    broken.write_text(broken.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    registry = RunRegistry(tmp_path / "ledger")
    try:
        report = registry.rebuild_index(tmp_path / "bundles")
        assert report.indexed == () and report.failures and registry.list_runs() == []
    finally:
        registry.close()


def test_lineage_ancestors_descendants_and_cycle_rule(tmp_path):
    registry = RunRegistry(tmp_path / "ledger")
    try:
        bundles = [_bundle(tmp_path / "bundles", _run(name, 1, environment=EnvironmentManifest())) for name in ("RUN-A", "RUN-B", "RUN-C")]
        for bundle in bundles:
            registry.register_run(bundle)
        registry.add_dependency(RunDependency("RUN-B", "RUN-A", "depends_on"))
        registry.add_dependency(RunDependency("RUN-C", "RUN-B", "derived_from"))
        assert registry.get_ancestors("RUN-C") == ("RUN-B", "RUN-A")
        assert registry.get_descendants("RUN-A") == ("RUN-B", "RUN-C")
        with pytest.raises(LineageCycleError) as error:
            registry.add_dependency(RunDependency("RUN-A", "RUN-C", "depends_on"))
        assert error.value.rule_id == "LEDGER-LINEAGE-CYCLE-001"
    finally:
        registry.close()


def test_claim_evidence_provenance_and_model_traces(tmp_path):
    manifest = _run("RUN-TRACE", 7, environment=EnvironmentManifest(), model_id="MODEL-1")
    claim = ScientificClaim("the fixture value is seven", manifest.run_id, (manifest.evidence[0].evidence_id,), EvidenceLevel.E2_COMPUTATIONAL, ClaimStatus.SUPPORTED)
    bundle = _bundle(tmp_path / "bundles", manifest, claim=claim)
    registry = RunRegistry(tmp_path / "ledger")
    try:
        registry.register_run(bundle)
        trace = registry.trace_claim(claim.claim_id)
        assert trace["evidence"][0]["provenance_ids"]
        assert registry.trace_evidence(manifest.evidence[0].evidence_id)["provenance"]
        assert registry.training_run_for_model("MODEL-1") == "RUN-TRAINING"
    finally:
        registry.close()


def test_content_addressed_packing_survives_source_removal(tmp_path):
    source = tmp_path / "result.txt"
    source.write_text("immutable result", encoding="utf-8")
    run = _run("RUN-ARTIFACT", 1, environment=EnvironmentManifest())
    bundle = _bundle(tmp_path / "bundles", run, artifact=source, pack_artifacts=True)
    source.unlink()
    assert bundle.verify().status == BundleVerificationStatus.PASS
    index = json.loads((Path(bundle.root) / "artifacts" / "index.json").read_text(encoding="utf-8"))
    digest = index["result.txt"]["artifact_hash"]
    store = ContentAddressedArtifactStore(Path(bundle.root) / "artifacts")
    assert store.verify_artifact(digest) and store.get_artifact(digest).is_file()


def _workflow_bundle(tmp_path: Path, plan_id: str = "PLAN-GOLDEN"):
    labs = LabRegistry()
    labs.register(GoldenFixtureLab("A", {"value": 1}))
    labs.register(GoldenFixtureLab("B", {"value": 2}))
    plan = WorkflowPlan((PlanStep("a", "A", {"x": 1}), PlanStep("b", "B", {"y": 2}, requires=("a",))), plan_id=plan_id)
    env = EnvironmentManifest(python={"version": "test"}, git={"commit": "fixture"})
    plan_run = ResearchOrchestrator(labs).run(plan)
    for child in plan_run.runs.values():
        child.attach_environment(env)
        child.seal()
    return ResearchBundle.create(plan_run, tmp_path / "bundles", environment=env), ResearchOrchestrator(labs), env


def test_workflow_rerun_reproduced_and_first_divergence_is_materialized(tmp_path):
    bundle, runner, env = _workflow_bundle(tmp_path)
    registry = RunRegistry(tmp_path / "ledger")
    try:
        registry.register_run(bundle)
        rerun = registry.rerun_workflow("PLAN-GOLDEN", runner=runner, output_root=tmp_path / "reruns", environment=env)
        assert rerun.comparison.status.value == "REPRODUCED"
        assert rerun.comparison.first_divergence is None
        changed = LabRegistry()
        changed.register(GoldenFixtureLab("A", {"value": 999}))
        changed.register(GoldenFixtureLab("B", {"value": 2}))
        divergent = registry.rerun_workflow("PLAN-GOLDEN", runner=ResearchOrchestrator(changed), output_root=tmp_path / "divergent", environment=env)
        assert divergent.comparison.status.value == "DIVERGED"
        assert divergent.comparison.first_divergence_step == "a"
        assert registry.verify_ledger().status == "PASS"
    finally:
        registry.close()


def test_indeterminate_workflow_indexes_skipped_descendants(tmp_path):
    result = run_deliberate_failure(tmp_path / "indeterminate")
    registry = RunRegistry(tmp_path / "ledger")
    try:
        registry.register_run(result.bundle)
        workflow = registry.get_workflow(result.plan_run.plan_id)
        assert workflow.status == "INDETERMINATE"
        assert workflow.first_loss_step_id == "combustion"
        assert [step.status for step in workflow.steps if step.step_id in {"thermal", "propulsion"}] == ["SKIPPED", "SKIPPED"]
    finally:
        registry.close()


def test_environment_change_is_distinguished_from_result_divergence(tmp_path):
    bundle, runner, _ = _workflow_bundle(tmp_path)
    registry = RunRegistry(tmp_path / "ledger")
    try:
        registry.register_run(bundle)
        changed_env = EnvironmentManifest(python={"version": "different"}, git={"commit": "fixture"})
        rerun = registry.rerun_workflow("PLAN-GOLDEN", runner=runner, output_root=tmp_path / "reruns", environment=changed_env)
        assert rerun.comparison.status.value == "REPRODUCED_WITH_ENVIRONMENT_CHANGE"
    finally:
        registry.close()


def test_retention_removes_index_only_and_schema_is_version_checked(tmp_path):
    bundle = _bundle(tmp_path / "bundles", _run("RUN-RETAIN", 1, environment=EnvironmentManifest()))
    registry = RunRegistry(tmp_path / "ledger")
    registry.register_run(bundle)
    assert registry.remove_index_entry("RUN-RETAIN").status.value == "REMOVED"
    assert Path(bundle.root).is_dir() and bundle.verify().status == BundleVerificationStatus.PASS
    db_path = registry.db_path
    registry.close()
    import sqlite3
    connection = sqlite3.connect(db_path)
    connection.execute("PRAGMA user_version=999")
    connection.commit()
    connection.close()
    with pytest.raises(Exception) as error:
        RunRegistry(db_path)
    assert "schema" in str(error.value).lower()
