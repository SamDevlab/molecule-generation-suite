from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.core.types import Evidence, EvidenceLevel, GateResult, GateStatus, RunManifest
from research_os.molecular_discovery import (
    FrozenESOLSolubilityPredictor,
    MolecularDiscoveryWorkflow,
    SolubilityCapabilityError,
    SolubilityPrediction,
)
from research_os.molecular_discovery.solubility import SolubilityRecord, parse_esol_csv


class FakeMoleculeLab:
    def run(self, raw, experiment="test"):
        manifest = RunManifest(lab="FakeMoleculeLab", experiment=experiment, inputs=dict(raw))
        manifest.start()
        if raw.get("smiles") == "INVALID":
            manifest.gates.append(
                GateResult("GATE-MOL", "MOL-STRUCT-002", GateStatus.FAIL, "invalid structure")
            )
            return manifest
        evidence = Evidence(
            evidence_id="EVD-MOL",
            kind="deterministic_molecular_properties",
            level=EvidenceLevel.E2_COMPUTATIONAL,
            source="fake",
            payload={"canonical_smiles": raw["smiles"], "molecular_weight": 100.0},
        )
        manifest.evidence.append(evidence)
        manifest.gates.append(
            GateResult("GATE-MOL", "MOL-STRUCT-002", GateStatus.PASS, "valid structure", evidence_ids=(evidence.evidence_id,))
        )
        manifest.complete()
        return manifest


class FakePredictor:
    def predict(self, smiles):
        values = {
            "CCO": (-0.5, 0.80, True),
            "CCC": (-1.5, 0.70, True),
            "CO": (-0.2, 0.10, False),
        }
        predicted, similarity, in_domain = values[smiles]
        return SolubilityPrediction(
            smiles=smiles,
            predicted_log_s_mol_l=predicted,
            max_training_tanimoto=similarity,
            applicability_threshold=0.26,
            in_domain=in_domain,
        )

    def evidence_manifest(self):
        return {"model_identity": "fake-model", "evidence_level": "E1_ML"}


def test_parse_esol_csv_reads_measured_target():
    records = parse_esol_csv(
        "Compound ID,smiles,measured log solubility in mols per litre\n"
        "A,CCO,-0.5\n"
        "B,CCC,-1.2\n"
    )
    assert [item.compound_id for item in records] == ["A", "B"]
    assert [item.measured_log_s_mol_l for item in records] == [-0.5, -1.2]


def test_frozen_predictor_rejects_dataset_identity_drift_before_training():
    with pytest.raises(SolubilityCapabilityError, match="dataset identity mismatch"):
        FrozenESOLSolubilityPredictor.fit(
            [SolubilityRecord("A", "CCO", -0.5)],
            enforce_frozen_identity=True,
        )


def test_workflow_prioritizes_complete_in_domain_evidence_without_composite_score(tmp_path: Path):
    workflow = MolecularDiscoveryWorkflow(
        molecule_lab=FakeMoleculeLab(),
        solubility_predictor=FakePredictor(),
        docking_lab=None,
    )
    report = workflow.run_to_directory(
        [
            {"id": "B", "smiles": "CCC"},
            {"id": "A", "smiles": "CCO"},
            {"id": "OOD", "smiles": "CO"},
            {"id": "BAD", "smiles": "INVALID"},
        ],
        tmp_path / "run",
    )

    assert [item.candidate_id for item in report.candidates] == ["A", "B", "OOD", "BAD"]
    assert report.candidates[0].priority_group == "ELIGIBLE_FOR_REVIEW"
    assert report.candidates[2].priority_group == "OUT_OF_DOMAIN"
    assert report.candidates[3].priority_group == "EXCLUDED"
    assert report.solubility_capability["model_identity"] == "fake-model"
    assert len(report.scientific_summary_hash) == 64

    root = tmp_path / "run"
    assert {path.name for path in root.iterdir()} == {
        "manifest.json",
        "evidence.json",
        "limitations.json",
        "candidates.csv",
        "report.md",
    }
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["candidate_count"] == 4
    assert manifest["scientific_summary_hash"] == report.scientific_summary_hash


def test_workflow_without_predictor_is_explicitly_incomplete():
    workflow = MolecularDiscoveryWorkflow(
        molecule_lab=FakeMoleculeLab(),
        solubility_predictor=None,
        docking_lab=None,
    )
    result = workflow.run([{"id": "A", "smiles": "CCO"}]).candidates[0]
    assert result.solubility_status == "UNAVAILABLE"
    assert result.priority_group == "INCOMPLETE_EVIDENCE"
