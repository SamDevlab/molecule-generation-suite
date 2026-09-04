from research_os.artifacts import ModelArtifactManifest
from research_os.core.hashing import sha256_file


def test_model_manifest_binds_model_dataset_and_training_run(tmp_path):
    model = tmp_path / "model.pkl"
    model.write_bytes(b"fake-model-for-manifest-test")
    manifest = ModelArtifactManifest.from_model_file(
        model_id="PHARMA-SOLUBILITY-XGB-001", task="aqueous_solubility",
        training_run_id="RUN-TRAIN-001", dataset_id="SOLUBILITY-v1", dataset_hash="a" * 64,
        feature_schema_id="MOL-MORGAN-R2-2048-v1", metrics={"mae": 0.42, "rmse": 0.63, "r2": 0.81},
        framework="xgboost", framework_version="test", model_file=model,
    )
    assert manifest.model_hash == sha256_file(model)
    out = manifest.write(tmp_path / "model.manifest.json")
    assert out.exists()
    assert len(manifest.manifest_hash) == 64
