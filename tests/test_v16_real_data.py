from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.bundles import verify_bundle
from research_os.core.types import GateStatus
from research_os.datasets import AQSOLDB_G_SAMPLE_SPEC, AQSOLDB_G_SPEC, DatasetSourceType, ingest_aqsoldb_g, validate_real_aqsoldb_g
from research_os.ledger import RunRegistry
from research_os.ml import MorganTanimotoApplicabilityDomain, make_real_split, rank_in_domain, run_real_data_golden, train_real_solubility_model
from research_os.molecule.features import MorganFeaturizer


SAMPLE = Path(__file__).resolve().parents[1] / "examples" / "real_data" / "aqsoldb_g_sample.csv"


def test_aqsoldb_sample_is_real_experimental_data_with_manifest_metadata(tmp_path: Path):
    pytest.importorskip("pyarrow")
    validation = validate_real_aqsoldb_g(SAMPLE, spec=AQSOLDB_G_SAMPLE_SPEC)
    assert validation.status == GateStatus.PASS
    result = ingest_aqsoldb_g(SAMPLE, tmp_path / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    manifest = result.manifest
    assert manifest.row_count == 46
    assert manifest.target == "Solubility"
    assert manifest.units == "log10(mol/L)"
    assert manifest.conditions["temperature_celsius"] == 25.0
    assert manifest.source_types == (DatasetSourceType.CURATED_EXPERIMENTAL,)
    assert manifest.experimental_fraction == 1.0
    assert manifest.synthetic_fraction == 0.0
    assert manifest.license == "CC0-1.0"
    assert manifest.source_url == AQSOLDB_G_SPEC.source_url
    assert manifest.source_file_hash == result.source.source_sha256
    assert Path(manifest.artifact_path or "").is_file()
    assert result.records[0]["target"] == -2.18


def test_scaffold_split_manifest_and_real_metrics_are_traceable(tmp_path: Path):
    pytest.importorskip("pyarrow")
    ingestion = ingest_aqsoldb_g(SAMPLE, tmp_path / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    data_split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, strategy="scaffold_split", split_id="SPLIT-TEST-REAL")
    assert split_manifest.strategy.value == "scaffold_split"
    assert split_manifest.counts == {"train": 31, "validation": 5, "test": 10, "external_test": 0}
    assert not set(split_manifest.train_ids) & set(split_manifest.validation_ids)
    assert not set(split_manifest.train_ids) & set(split_manifest.test_ids)
    ml = train_real_solubility_model(ingestion.records, ingestion.manifest, tmp_path / "ml", data_split=data_split, split_manifest=split_manifest, model_id="MODEL-TEST-REAL", training_run_id="TRN-TEST-REAL")
    assert set(ml.validation.metrics) == {"MAE", "RMSE", "R2"}
    assert all(isinstance(value, float) for value in ml.validation.metrics.values())
    assert ml.validation.applicability_domain is not None
    assert ml.validation.calibration["method"] == "absolute_residual_quantile"
    assert "approximate certainty" not in json.dumps(ml.validation.calibration).lower()
    assert ml.training_run.dataset_id == ingestion.manifest.dataset_id
    assert Path(ml.model_artifact.model_file or "").is_file()
    assert Path(tmp_path / "ml" / "models" / "split-manifest.json").is_file()


def test_tanimoto_ad_marks_ood_and_excludes_it_from_ranking(tmp_path: Path):
    pytest.importorskip("pyarrow")
    ingestion = ingest_aqsoldb_g(SAMPLE, tmp_path / "datasets", spec=AQSOLDB_G_SAMPLE_SPEC)
    split, split_manifest = make_real_split(ingestion.records, ingestion.manifest, split_id="SPLIT-TEST-AD")
    ml = train_real_solubility_model(ingestion.records, ingestion.manifest, tmp_path / "ml", data_split=split, split_manifest=split_manifest, model_id="MODEL-TEST-AD", training_run_id="TRN-TEST-AD")
    known = next(record["smiles"] for record in ingestion.records if record["compound_id"] in split_manifest.train_ids)
    known_prediction = ml.model.predict(known)
    assert known_prediction.in_domain is True
    assert known_prediction.ood_score == pytest.approx(0.0)
    assert known_prediction.model_id == "MODEL-TEST-AD"
    assert known_prediction.dataset_id == ingestion.manifest.dataset_id
    assert known_prediction.feature_schema_id == ml.feature_schema.feature_schema_id
    assert known_prediction.run_id == "TRN-TEST-AD"
    ad = MorganTanimotoApplicabilityDomain(MorganFeaturizer().transform_one("CCO")[None, :], threshold=0.99)
    ood = ad.assess_smiles("C#N")
    assert ood.in_domain is False
    assert rank_in_domain((known_prediction,)) == (known_prediction,)


def test_real_golden_run_bundle_and_ledger_preserve_first_loss(tmp_path: Path):
    pytest.importorskip("pyarrow")
    result = run_real_data_golden(tmp_path, repo_root=Path(__file__).resolve().parents[1])
    assert result.run.run_id == "REAL-DATA-GOLDEN-RUN"
    assert result.run.status == "SEALED"
    assert result.promotion.status.value == "REJECTED"
    assert result.promotion.champion_model_id == "MODEL-AQSOLDB-G-REAL-SAMPLE-REAL-BASELINE"
    assert result.run.first_loss_rule_id == "ML-PROMO-EXT-001"
    assert result.verification.passed
    assert result.ledger_record.model_ids == ("MODEL-AQSOLDB-G-REAL-GOLDEN", "MODEL-AQSOLDB-G-REAL-SAMPLE-REAL-BASELINE")
    assert len(result.ledger_record.evidence_ids) == 4
    assert result.ledger_record.first_loss_rule_id == "ML-PROMO-EXT-001"
    manifest = json.loads((Path(result.bundle.root) / "manifest.json").read_text(encoding="utf-8"))
    assert len(manifest["evidence"]) == 4
    assert len(manifest["gates"]) == 8
    assert len(manifest["provenance"]) == 1
    assert verify_bundle(result.bundle.root).passed
    with RunRegistry(tmp_path / "ledger") as ledger:
        claim_trace = ledger.trace_claim(result.claim.claim_id)
        evidence_trace = ledger.trace_evidence(result.ledger_record.evidence_ids[1])
        assert claim_trace["run"]["run_id"] == result.run.run_id
        assert evidence_trace["run"]["run_id"] == result.run.run_id
        assert evidence_trace["provenance"]
