from pathlib import Path

import pytest

from research_os.artifacts import ModelArtifactManifest
from research_os.biolab import BiolabConfig, BiolabRunner, load_biolab_config
from research_os.core.types import EvidenceLevel, GateStatus
from research_os.datasets import DatasetManifest, DatasetRegistry, DatasetSourceType, dataset_ground_truth_gate
from research_os.knowledge import ReviewStatus, SourceLocator, Zettel, ZettelType, zettel_to_training_record
from research_os.ml import ModelPromotionEngine, PromotionStatus, SplitStrategy, compute_regression_metrics, group_split, validate_regression
from research_os.metal import MetalLab
from research_os.orchestration import LabRegistry, PlanStep, ResearchOrchestrator


def test_biolab_config_is_typed_and_target_grids_are_independent():
    config = load_biolab_config(Path("configs/biolab.yaml"))
    assert config.vina.exhaustiveness == 8
    assert config.compute.max_workers == 4
    assert config.target("1cx2").grid.size_x == 20.0
    assert config.target("4cox").role == "COX1"


def test_biolab_missing_vina_is_indeterminate(tmp_path):
    class MissingVina:
        available = False
        version = None

    receptor = tmp_path / "r.pdbqt"
    ligand = tmp_path / "l.pdbqt"
    receptor.write_text("RECEPTOR")
    ligand.write_text("LIGAND")
    config = BiolabConfig.from_mapping({"targets": {"target": {"role": "test", "receptor": str(receptor), "grid": {"center": [0, 0, 0], "size": [10, 10, 10]}}}})
    run = BiolabRunner(config, vina_engine=MissingVina()).run_target("target", ligand_path=ligand)
    assert run.first_loss is not None
    assert run.first_loss.status == GateStatus.INDETERMINATE


def test_regression_metrics_do_not_create_reliability_percent():
    metrics = compute_regression_metrics([1, 2, 3], [1, 2, 4]).to_dict()
    assert set(metrics) == {"MAE", "RMSE", "R2"}
    assert "reliability_percent" not in metrics
    report = validate_regression([1, 2], [1, 2], split_strategy="external_test", external_test_acceptable=True)
    assert report.passed
    assert report.split_strategy == SplitStrategy.EXTERNAL_TEST


def test_group_split_keeps_groups_together():
    records = [{"id": i, "group_id": i // 2} for i in range(20)]
    split = group_split(records, validation_size=0.2, test_size=0.2)
    locations = {}
    for name, bucket in (("train", split.train), ("validation", split.validation), ("test", split.test)):
        for record in bucket:
            previous = locations.setdefault(record["group_id"], name)
            assert previous == name


def _model(model_id: str, mae: float) -> ModelArtifactManifest:
    return ModelArtifactManifest(model_id=model_id, task="solubility", framework="test", framework_version="1", training_run_id=f"RUN-{model_id}", dataset_id="DS-1", dataset_hash="a" * 64, feature_schema_id="features-v1", split_strategy="random_split", train_count=8, validation_count=1, test_count=1, seed=42, metrics={"MAE": mae, "RMSE": mae, "R2": 0.9}, git_commit="abc")


def test_bad_candidate_does_not_replace_champion_and_decision_is_evidence_backed():
    champion = _model("champion", 0.2)
    candidate = _model("candidate", 0.4)
    validation = validate_regression([1, 2], [1, 2], model_id="candidate", external_test_acceptable=True)
    decision = ModelPromotionEngine().evaluate(candidate, champion, validation=validation)
    assert decision.status == PromotionStatus.REJECTED
    assert decision.evidence.level == EvidenceLevel.E1_ML
    assert "ML-PROMO-MAE-001" in decision.evidence.payload["rule_ids"]


def test_dataset_hash_changes_and_synthetic_data_cannot_be_experimental():
    registry = DatasetRegistry()
    first = registry.register_records(dataset_id="predictions", version="1", schema_id="schema-v1", records=[{"x": 1}], source_types=(DatasetSourceType.ML_GENERATED,), synthetic_fraction=1.0)
    second = DatasetManifest.from_records(dataset_id="predictions", version="2", schema_id="schema-v1", records=[{"x": 2}], source_types=(DatasetSourceType.ML_GENERATED,), synthetic_fraction=1.0)
    assert first.sha256 != second.sha256
    assert dataset_ground_truth_gate(first).status == GateStatus.INSUFFICIENT_EVIDENCE


def test_metal_optional_feature_engine_fails_closed():
    run = MetalLab().run({"composition": {"Ni": 0.8, "Cr": 0.2}, "fraction_basis": "atomic", "features": ["VEC"]})
    assert run.first_loss is not None
    assert run.first_loss.rule_id == "MET-FEATURE-001"
    assert run.first_loss.status == GateStatus.INDETERMINATE


def test_workflow_records_provenance_and_skips_downstream():
    from research_os.molecule import MoleculeLab

    registry = LabRegistry()
    registry.register(MoleculeLab(), aliases=("molecule",))
    plan = ResearchOrchestrator(registry).run([
        PlanStep("bad", "molecule", {"smiles": "not a smiles"}),
        PlanStep("downstream", "molecule", {"smiles": "CCO"}, requires=("bad",)),
    ])
    assert plan.steps["bad"].first_loss is not None
    assert plan.steps["downstream"].status == "SKIPPED"
    assert plan.steps["downstream"].first_loss.status == GateStatus.SKIPPED
    assert "upstream" in plan.steps["downstream"].skip_reason


def test_unreviewed_zettel_cannot_enter_training_record():
    zettel = Zettel(title="Draft", summary="Draft summary", zettel_type=ZettelType.CONCEPT, domain="test", evidence_level=EvidenceLevel.E0_HEURISTIC, review_status=ReviewStatus.REVIEW_REQUIRED, sources=(SourceLocator(source_id="SRC-1"),))
    with pytest.raises(ValueError, match="VERIFIED"):
        zettel_to_training_record(zettel)
