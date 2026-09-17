from __future__ import annotations

from copy import deepcopy

from research_os.docking.redocking_v12_identity import scientific_result_hash


def _report() -> dict:
    return {
        "protocol_id": "research-os.redocking.v1.2",
        "symmetry_mapping_max_matches": 10000,
        "frozen_cases": [{"case_id": "RDK-001", "pdb_id": "1STP", "ligand_id": "BTN"}],
        "records": [
            {
                "case": {"case_id": "RDK-001", "pdb_id": "1STP", "ligand_id": "BTN"},
                "result": {"case_id": "RDK-001", "status": "PASS", "pose_1_rmsd_angstrom": 1.2345678901234, "minimum_rmsd_angstrom": 1.1, "pose_count": 3, "vina_pose_1_score_kcal_mol": -7.2, "first_loss": None, "pose_1_success": True},
                "provenance": {
                    "protocol_id": "research-os.redocking.v1.2",
                    "raw_pdb": {"url": "https://example.invalid/1STP.pdb", "sha256": "a" * 64},
                    "extraction": {"ligand_auth_seq_id": 300, "ligand_insertion_code": "", "ligand_heavy_atoms_from_pdb": 16, "receptor_atom_count": 1000, "receptor_sha256": "b" * 64, "native_ligand_pdb_sha256": "c" * 64},
                    "reference": {"url": "https://example.invalid/ref.sdf", "sha256": "d" * 64, "heavy_atoms": 16},
                    "grid": {"center_x": 1.0, "center_y": 2.0, "center_z": 3.0, "size_x": 20.0, "size_y": 20.0, "size_z": 20.0, "grid_hash": "e" * 64, "status": "PASS"},
                    "starting_conformer": {"sha256": "f" * 64, "uff_optimized": True, "random_seed": 42, "heavy_atoms": 16},
                    "engines": {"openbabel": {"path": "/usr/bin/obabel", "version": "Open Babel 3.1.1"}, "vina": {"path": "/tmp/vina", "version": "AutoDock Vina v1.2.7"}},
                    "preparation": {
                        "receptor": {"input_path": "/tmp/a", "output_path": "/tmp/b", "returncode": 0, "engine": "Open Babel", "engine_version": "Open Babel 3.1.1", "status": "SUPPORTED_AND_EXECUTED", "input_sha256": "b" * 64, "output_sha256": "1" * 64, "timed_out": False, "protocol_id": "redocking.v1.2.receptor-openbabel", "elapsed_seconds": 0.5, "stdout": "runtime text"},
                        "ligand": {"input_path": "/tmp/c", "output_path": "/tmp/d", "returncode": 0, "engine": "Open Babel", "engine_version": "Open Babel 3.1.1", "status": "SUPPORTED_AND_EXECUTED", "input_sha256": "f" * 64, "output_sha256": "2" * 64, "timed_out": False, "protocol_id": "redocking.v1.2.ligand-openbabel", "elapsed_seconds": 0.2},
                    },
                    "docking": {"best_affinity_kcal_mol": -7.2, "output_path": "/tmp/out", "returncode": 0, "engine": "AutoDock Vina", "engine_version": "AutoDock Vina v1.2.7", "status": "SUPPORTED_AND_EXECUTED", "receptor_sha256": "1" * 64, "ligand_sha256": "2" * 64, "output_sha256": "3" * 64, "log_sha256": "4" * 64, "grid_hash": "e" * 64, "target_id": "1STP", "protocol_id": "research-os.redocking.v1.2", "timed_out": False, "stdout": "runtime output"},
                },
                "poses": [{"rank": 1, "score_kcal_mol": -7.2, "status": "PASS", "rmsd_angstrom": 1.2345678901234, "reference_sha256": "8" * 64, "predicted_sha256": "9" * 64, "pdbqt_sha256": "5" * 64, "sdf_sha256": "6" * 64}],
            }
        ],
        "summary": {"protocol_id": "research-os.redocking.v1.2", "total_cases": 1, "passing_rmsd_cases": 1, "status_counts": {"PASS": 1}, "pose_1_rmsd_angstrom": {"mean_over_passing_cases": 1.2345678901234, "median_over_passing_cases": 1.2345678901234, "values": [1.2345678901234]}, "pose_1_rmsd_le_2_angstrom": {"count": 1, "fraction_all_frozen_cases": 1.0, "denominator": 1}, "cases": [], "summary_hash": "7" * 64},
        "environment": {"python": "3.12.14", "platform": "host-a"},
    }


def test_scientific_hash_ignores_runtime_paths_timing_and_stdout():
    left = _report()
    right = deepcopy(left)
    right["records"][0]["provenance"]["engines"]["vina"]["path"] = "/another/vina"
    right["records"][0]["provenance"]["preparation"]["receptor"]["elapsed_seconds"] = 99.9
    right["records"][0]["provenance"]["preparation"]["receptor"]["stdout"] = "different"
    right["records"][0]["provenance"]["docking"]["output_path"] = "/another/out"
    right["records"][0]["provenance"]["docking"]["stdout"] = "different output"
    right["environment"] = {"python": "3.13.0", "platform": "host-b"}
    assert scientific_result_hash(left) == scientific_result_hash(right)


def test_scientific_hash_ignores_volatile_sdf_representation_hashes():
    left = _report()
    right = deepcopy(left)
    record = right["records"][0]
    record["provenance"]["reference"]["sha256"] = "0" * 64
    record["provenance"]["starting_conformer"]["sha256"] = "a" * 64
    record["provenance"]["preparation"]["ligand"]["input_sha256"] = "b" * 64
    record["poses"][0]["reference_sha256"] = "c" * 64
    record["poses"][0]["predicted_sha256"] = "d" * 64
    record["poses"][0]["sdf_sha256"] = "e" * 64
    assert scientific_result_hash(left) == scientific_result_hash(right)


def test_scientific_hash_normalizes_irrelevant_float_noise():
    left = _report()
    right = deepcopy(left)
    right["records"][0]["result"]["pose_1_rmsd_angstrom"] += 1e-14
    right["records"][0]["poses"][0]["rmsd_angstrom"] += 1e-14
    right["summary"]["pose_1_rmsd_angstrom"]["values"][0] += 1e-14
    right["summary"]["pose_1_rmsd_angstrom"]["mean_over_passing_cases"] += 1e-14
    right["summary"]["pose_1_rmsd_angstrom"]["median_over_passing_cases"] += 1e-14
    assert scientific_result_hash(left) == scientific_result_hash(right)


def test_scientific_hash_changes_for_material_rmsd_change():
    left = _report()
    right = deepcopy(left)
    right["records"][0]["result"]["pose_1_rmsd_angstrom"] = 1.5
    right["records"][0]["poses"][0]["rmsd_angstrom"] = 1.5
    right["summary"]["pose_1_rmsd_angstrom"]["values"] = [1.5]
    right["summary"]["pose_1_rmsd_angstrom"]["mean_over_passing_cases"] = 1.5
    right["summary"]["pose_1_rmsd_angstrom"]["median_over_passing_cases"] = 1.5
    assert scientific_result_hash(left) != scientific_result_hash(right)


def test_scientific_hash_changes_for_stable_pose_pdbqt_content_change():
    left = _report()
    right = deepcopy(left)
    right["records"][0]["poses"][0]["pdbqt_sha256"] = "0" * 64
    assert scientific_result_hash(left) != scientific_result_hash(right)
