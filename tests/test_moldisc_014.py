from __future__ import annotations

from pathlib import Path

import pytest
from rdkit import Chem, DataStructs
from rdkit.Chem import rdFingerprintGenerator

from research_os.molecular_discovery.aqsoldb_coverage import AqSolDBSourceRecord
from research_os.molecular_discovery.moldisc014 import (
    CONTEXT_MOLDISC013_HASH,
    DELTA_BOTH_HEAVY_ATOMS,
    DELTA_BOTH_INCHIKEY,
    DELTA_BOTH_SMILES,
    DELTA_BOTH_VARIANT_ID,
    DELTA_NSUB_HEAVY_ATOMS,
    DELTA_NSUB_INCHIKEY,
    DELTA_NSUB_SMILES,
    DELTA_NSUB_VARIANT_ID,
    DELTA_OH_HEAVY_ATOMS,
    DELTA_OH_INCHIKEY,
    DELTA_OH_SMILES,
    DELTA_OH_VARIANT_ID,
    MOLDISC014Error,
    PARENT_MOLDISC011_HASH,
    SEED_CANDIDATE_ID,
    SEED_HEAVY_ATOMS,
    SEED_INCHIKEY,
    SEED_SMILES,
    SOURCE_CANONICAL_SMILES,
    SOURCE_CONNECTIVITY_BLOCK,
    SOURCE_INCHIKEY,
    SOURCE_MEASURED_LOG_S,
    SOURCE_RAW_SMILES,
    audit_frozen_source,
    generate_panel,
    load_program_config_v14,
    measurement_transfer_decision,
)


CONFIG = Path("programs/moldisc-014-aqsoldb-source-interpolation/program.json")


def _source_records() -> tuple[AqSolDBSourceRecord, ...]:
    return (AqSolDBSourceRecord("C-2545", SOURCE_RAW_SMILES, SOURCE_MEASURED_LOG_S, SOURCE_INCHIKEY),)


def test_protocol_freezes_upstream_source_panel_and_boundaries():
    config = load_program_config_v14(CONFIG)
    assert config["upstream"]["moldisc011_program_scientific_hash"] == PARENT_MOLDISC011_HASH
    assert config["upstream"]["moldisc013_program_scientific_hash"] == CONTEXT_MOLDISC013_HASH
    assert config["seed"]["candidate_id"] == SEED_CANDIDATE_ID
    assert config["seed"]["canonical_smiles"] == SEED_SMILES
    assert config["seed"]["inchikey"] == SEED_INCHIKEY
    assert config["source"]["expected_canonical_nonisomeric_smiles"] == SOURCE_CANONICAL_SMILES
    assert config["source"]["expected_inchikey"] == SOURCE_INCHIKEY
    assert config["boundaries"]["source_measurement_used_for_generation"] is False
    assert config["boundaries"]["candidate_selection_executed"] is False
    assert config["boundaries"]["docking_executed"] is False


def test_generation_is_exactly_seed_plus_three_expected_products():
    panel = generate_panel()
    assert [item.variant_id for item in panel] == [
        "STEP2-DEMETHYL-01",
        DELTA_OH_VARIANT_ID,
        DELTA_NSUB_VARIANT_ID,
        DELTA_BOTH_VARIANT_ID,
    ]
    assert [item.heavy_atom_count for item in panel] == [
        SEED_HEAVY_ATOMS,
        DELTA_OH_HEAVY_ATOMS,
        DELTA_NSUB_HEAVY_ATOMS,
        DELTA_BOTH_HEAVY_ATOMS,
    ]
    assert [item.canonical_smiles for item in panel] == [
        SEED_SMILES,
        DELTA_OH_SMILES,
        DELTA_NSUB_SMILES,
        DELTA_BOTH_SMILES,
    ]
    assert [item.inchikey for item in panel] == [
        SEED_INCHIKEY,
        DELTA_OH_INCHIKEY,
        DELTA_NSUB_INCHIKEY,
        DELTA_BOTH_INCHIKEY,
    ]
    assert len({item.canonical_smiles for item in panel}) == 4
    assert all(item.canonical_smiles != SEED_SMILES for item in panel[1:])
    assert all(item.evidence_level == "E0_HEURISTIC" for item in panel)


def test_source_audit_preserves_raw_identity_ids_measurement_and_missing_stereo():
    audit = audit_frozen_source(
        _source_records(),
        source_row_count=9982,
        parsed_source_hash="2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4",
    )
    assert audit.source_ids == ("C-2545",)
    assert audit.raw_source_smiles == SOURCE_RAW_SMILES
    assert audit.canonical_nonisomeric_smiles == SOURCE_CANONICAL_SMILES
    assert audit.active_runtime_inchikey == SOURCE_INCHIKEY
    assert audit.connectivity_inchikey_block == SOURCE_CONNECTIVITY_BLOCK
    assert audit.observation_count == 1
    assert audit.measured_log_s_values == (-3.62,)
    assert audit.stereo_specified is False


def test_source_drift_fails_closed():
    with pytest.raises(MOLDISC014Error):
        audit_frozen_source(
            (AqSolDBSourceRecord("DRIFT", SOURCE_RAW_SMILES, SOURCE_MEASURED_LOG_S, SOURCE_INCHIKEY),),
            source_row_count=9982,
            parsed_source_hash="2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4",
        )


def test_delta_both_has_fingerprint_one_but_no_exact_stereochemical_transfer():
    panel = generate_panel()
    both = next(item for item in panel if item.variant_id == DELTA_BOTH_VARIANT_ID)
    source = audit_frozen_source(
        _source_records(),
        source_row_count=9982,
        parsed_source_hash="2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4",
    )
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=2, fpSize=2048)
    source_fp = generator.GetFingerprint(Chem.MolFromSmiles(SOURCE_CANONICAL_SMILES))
    candidate_fp = generator.GetFingerprint(Chem.MolFromSmiles(both.canonical_smiles))
    assert DataStructs.TanimotoSimilarity(source_fp, candidate_fp) == pytest.approx(1.0)
    decision = measurement_transfer_decision(both, source)
    assert decision["same_connectivity_as_recurring_source"] is True
    assert decision["full_inchikey_match_to_recurring_source"] is False
    assert decision["exact_canonical_match"] is False
    assert decision["measurement_transfer_allowed"] is False


def test_seed_and_single_deltas_do_not_transfer_source_measurement():
    panel = generate_panel()
    source = audit_frozen_source(
        _source_records(),
        source_row_count=9982,
        parsed_source_hash="2c6e56f56389f0fd99fa2a3c843446f98b6b068a3f93aaab71a08822caa085f4",
    )
    for item in panel[:3]:
        decision = measurement_transfer_decision(item, source)
        assert decision["measurement_transfer_allowed"] is False


def test_protocol_has_no_docking_or_selection_code_boundary():
    text = CONFIG.read_text(encoding="utf-8")
    assert '"candidate_selection_executed": false' in text
    assert '"selected_candidate_id": null' in text
    assert '"docking_executed": false' in text
    assert '"source_measurement_used_for_ranking": false' in text
