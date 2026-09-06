from research_os.docking.contract import DockingExecutionContract


def raw_request(tmp_path):
    return {
        "protocol_id": "autodock-vina.docking.v1",
        "receptor_path": str(tmp_path / "receptor.pdbqt"),
        "ligand_path": str(tmp_path / "ligand.pdbqt"),
        "grid": {"center_x": 0, "center_y": 0, "center_z": 0, "size_x": 20, "size_y": 20, "size_z": 20},
        "seed": 42, "exhaustiveness": 8, "cpu": 1, "num_modes": 9, "timeout": 30,
        "target_id": "TARGET-COX2", "species": "Homo sapiens",
        "receptor_metadata": {"structure_id": "5KIR", "source_id": "SRC-RCSB-5KIR", "sha256": "a" * 64},
        "preparation_method": "openbabel.receptor-ligand-preparation.v1",
        "scoring_function": "vina_default",
        "protonation_assumptions": ("declared protonation retained",),
        "charge_method": "gasteiger",
        "engine_version": "vina-test",
    }


def test_docking_contract_is_explicit_and_e2_bounded(tmp_path):
    contract = DockingExecutionContract.from_mapping(raw_request(tmp_path))
    contract.validate(strict_provenance=True)
    assert contract.evidence_ceiling == "E2_COMPUTATIONAL"
    assert contract.contract_hash == contract.contract_hash
    assert contract.to_dict()["grid"]["size_x"] == 20.0


def test_docking_contract_rejects_invalid_limits_and_evidence_ceiling(tmp_path):
    raw = raw_request(tmp_path)
    raw["cpu"] = 0
    contract = DockingExecutionContract.from_mapping(raw)
    try:
        contract.validate()
    except ValueError as exc:
        assert "positive" in str(exc)
    else:
        raise AssertionError("invalid CPU limit was accepted")
