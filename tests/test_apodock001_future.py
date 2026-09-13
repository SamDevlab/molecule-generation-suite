import json
from pathlib import Path

from rdkit import Chem

from research_os.docking.apodock001_future import (
    POSE_ADAPTER_ID,
    POSE_ADAPTER_VERSION,
    build_complete_raw_results_seal,
    classify_timeout_record,
    normalize_openbabel_pose_for_reference,
    scientific_pose_identity,
)


ROOT = Path(__file__).parents[1]


def test_future_raw_seal_requires_and_records_complete_identity() -> None:
    seal = build_complete_raw_results_seal(
        protocol_id="research-os.apodock001.protocol.v1.1+abc",
        protocol_hash="a" * 64,
        planned_run_id="research-os.apodock001.planned-run.v2+abc",
        run_id="research-os.apodock001.run.v2+abc",
        raw_output_hashes={"APD-002": "b" * 64, "APD-001": None},
    )
    assert seal["schema_version"] == "research-os.apodock001.raw-results-seal.v2"
    assert seal["protocol_hash"] == "a" * 64
    assert seal["planned_run_id"].endswith("+abc")
    assert seal["run_id"].endswith("+abc")
    assert list(seal["raw_output_hashes"]) == ["APD-001", "APD-002"]
    assert len(seal["raw_results_seal_sha256"]) == 64


def test_timeout_classification_is_fail_closed_and_no_retry() -> None:
    result = classify_timeout_record(
        {
            "status": "FAILED",
            "returncode": -1,
            "raw_output_sha256": None,
        }
    )
    assert result == {
        "stage": "ADAPTER_SUBPROCESS_TIMEOUT",
        "confidence": "HIGH",
        "is_timeout": True,
        "timeout_seconds": 900.0,
        "retry_count": 0,
        "raw_output_present": False,
    }


def test_apd007_like_valence_conversion_is_repaired_without_changing_raw_bytes() -> None:
    raw = ROOT / "runs" / "apodock001-v1.0.2" / "raw" / "APD-007" / "vina_poses.pdbqt"
    converted = (
        ROOT
        / "runs"
        / "apodock001-v1.0.2"
        / "analysis-derived"
        / "APD-007"
        / "pose_01.sdf"
    )
    reference = Chem.MolFromSmiles("[C][N+]([C])([C])[C]C(=O)O")
    assert reference is not None
    conformer = Chem.Conformer(reference.GetNumAtoms())
    for index in range(reference.GetNumAtoms()):
        conformer.SetAtomPosition(index, (float(index), 0.0, 0.0))
    reference.AddConformer(conformer)
    before = raw.read_bytes()
    repaired, mapping = normalize_openbabel_pose_for_reference(converted, reference)
    assert raw.read_bytes() == before
    assert repaired.GetNumHeavyAtoms() == reference.GetNumHeavyAtoms() == 8
    assert Chem.GetFormalCharge(repaired) == Chem.GetFormalCharge(reference) == 1
    assert len(mapping) == 8
    Chem.SanitizeMol(repaired)


def test_scientific_pose_identity_ignores_sdf_metadata_and_serialization(tmp_path: Path) -> None:
    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    assert molecule is not None
    conformer = Chem.Conformer(molecule.GetNumAtoms())
    for index in range(molecule.GetNumAtoms()):
        conformer.SetAtomPosition(index, (float(index), 0.5, -0.25))
    molecule.AddConformer(conformer)
    first = tmp_path / "first.sdf"
    second = tmp_path / "second.sdf"
    for path, title in ((first, "first title"), (second, "second title")):
        writer = Chem.SDWriter(str(path))
        molecule.SetProp("_Name", title)
        writer.write(molecule)
        writer.close()
    first_mol = Chem.SDMolSupplier(str(first), removeHs=False)[0]
    second_mol = Chem.SDMolSupplier(str(second), removeHs=False)[0]
    assert first_mol is not None and second_mol is not None
    mapping = tuple(range(first_mol.GetNumAtoms()))
    assert scientific_pose_identity(
        first_mol,
        source_raw_sha256="c" * 64,
        atom_mapping=mapping,
        adapter_id=POSE_ADAPTER_ID,
        adapter_version=POSE_ADAPTER_VERSION,
    ) == scientific_pose_identity(
        second_mol,
        source_raw_sha256="c" * 64,
        atom_mapping=mapping,
        adapter_id=POSE_ADAPTER_ID,
        adapter_version=POSE_ADAPTER_VERSION,
    )
