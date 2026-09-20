from __future__ import annotations

import json
import csv
from pathlib import Path

import pytest

from research_os.molecular_discovery.moldisc015 import (
    AQSOLDB_FORMULA,
    AQSOLDB_INCHI,
    AQSOLDB_INCHIKEY,
    AQSOLDB_RAW_SMILES,
    CONFLICTING_SOURCE_IDENTITIES,
    DATASET_C_REFERENCE_DOI,
    RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY,
    SOURCE_DELTA_BOTH_INCHIKEY,
    UNRESOLVED_SOURCE_STEREOCHEMISTRY,
    AqSolDBRecord,
    SupportingInformationArtifact,
    alias_identity_compatible,
    classify_resolution,
    derive_formula_from_inchi,
    inchi_stereochemistry_specified,
    load_program_config_v15,
    measurement_transfer_decision,
    parse_aqsoldb_csv,
)


def test_frozen_program_config_and_boundaries() -> None:
    config = load_program_config_v15("programs/moldisc-015-c2545-source-resolution/program.json")
    assert config["program_id"] == "MOLDISC-015"
    assert config["upstream"]["source_record_id"] == "C-2545"
    assert config["immutable_aqsoldb_lineage"]["dataset_c_readme_mapping"] == "3. dataset-C.csv [3]"
    assert config["boundaries"]["generation_executed"] is False
    assert config["boundaries"]["docking_executed"] is False
    assert config["boundaries"]["esol_executed"] is False
    assert config["boundaries"]["candidate_selection_executed"] is False


def test_aqsoldb_record_and_stereo_absence() -> None:
    assert derive_formula_from_inchi(AQSOLDB_INCHI) == AQSOLDB_FORMULA
    assert inchi_stereochemistry_specified(AQSOLDB_INCHI) is False
    record = AqSolDBRecord("C-2545", "phenyl-kni-727", AQSOLDB_RAW_SMILES, AQSOLDB_INCHI, AQSOLDB_INCHIKEY, -3.62)
    assert record.formula == "C27H35N3O4S"
    assert record.connectivity_block == "URHJIBSBOJFXDI"
    assert record.stereochemistry_specified is False


def test_csv_parser_preserves_raw_record(tmp_path: Path) -> None:
    csv_path = tmp_path / "dataset-C.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["ID", "Name", "SMILES", "InChI", "InChIKey", "Solubility"])
        writer.writeheader()
        writer.writerow({
            "ID": "C-2545",
            "Name": "phenyl-kni-727",
            "SMILES": AQSOLDB_RAW_SMILES,
            "InChI": AQSOLDB_INCHI,
            "InChIKey": AQSOLDB_INCHIKEY,
            "Solubility": "-3.62",
        })
    record = parse_aqsoldb_csv(csv_path)
    assert record.record_id == "C-2545"
    assert record.raw_fields["Name"] == "phenyl-kni-727"
    assert record.measured_log_s_mol_l == -3.62


def test_false_alias_requires_formula_and_connectivity() -> None:
    assert alias_identity_compatible(name="KNI-727", formula="C30H41N3O5S", connectivity_block="URHJIBSBOJFXDI") is False
    assert alias_identity_compatible(name="phenyl-kni-727", formula=AQSOLDB_FORMULA, connectivity_block="WRONG") is False
    assert alias_identity_compatible(name="unrelated-name", formula=AQSOLDB_FORMULA, connectivity_block="URHJIBSBOJFXDI") is True


def test_connectivity_only_does_not_transfer_measurement() -> None:
    result = measurement_transfer_decision(
        resolved_source_inchikey=AQSOLDB_INCHIKEY,
        resolved_source_canonical_isomeric_smiles="source-stereo",
        source_delta_both_inchikey=SOURCE_DELTA_BOTH_INCHIKEY,
        source_delta_both_canonical_isomeric_smiles="different-stereo",
        measured_record_attribution=True,
    )
    assert result == {
        "same_connectivity": True,
        "exact_stereo_identity": False,
        "full_inchikey_match": False,
        "measurement_transfer_allowed": False,
    }


def test_exact_resolved_fixture_allows_transfer() -> None:
    result = measurement_transfer_decision(
        resolved_source_inchikey=SOURCE_DELTA_BOTH_INCHIKEY,
        resolved_source_canonical_isomeric_smiles="exact-stereo",
        source_delta_both_inchikey=SOURCE_DELTA_BOTH_INCHIKEY,
        source_delta_both_canonical_isomeric_smiles="exact-stereo",
        measured_record_attribution=True,
    )
    assert result["measurement_transfer_allowed"] is True
    assert result["exact_stereo_identity"] is True


def test_resolution_statuses_are_fail_closed() -> None:
    assert classify_resolution(record_recoverable=False, connectivity_traceable=False, measurement_traceable=False) == "SOURCE_RECORD_NOT_RECOVERABLE"
    assert classify_resolution(record_recoverable=True, connectivity_traceable=True, measurement_traceable=True) == UNRESOLVED_SOURCE_STEREOCHEMISTRY
    assert classify_resolution(
        record_recoverable=True,
        connectivity_traceable=True,
        measurement_traceable=True,
        attributable_stereochemical_candidates=({"exact_identity": True}, {"exact_identity": True}),
    ) == CONFLICTING_SOURCE_IDENTITIES
    assert classify_resolution(
        record_recoverable=True,
        connectivity_traceable=True,
        measurement_traceable=True,
        attributable_stereochemical_candidates=({"exact_identity": True},),
    ) == RESOLVED_EXACT_STEREOCHEMICAL_IDENTITY


def test_supporting_information_hash_excludes_transport_time_and_temp_path() -> None:
    first = SupportingInformationArtifact(
        recovered=True,
        source_url="https://acs.example/file.pdf",
        publisher="ACS",
        filename="si.pdf",
        transport_sha256="a" * 64,
        file_size_bytes=10,
        retrieval_date="2026-01-01",
        publication_doi=DATASET_C_REFERENCE_DOI,
        temporary_path="C:/temp/one.pdf",
    )
    second = SupportingInformationArtifact(
        recovered=True,
        source_url="https://acs.example/file.pdf",
        publisher="ACS",
        filename="si.pdf",
        transport_sha256="a" * 64,
        file_size_bytes=10,
        retrieval_date="2026-02-01",
        publication_doi=DATASET_C_REFERENCE_DOI,
        temporary_path="D:/temp/two.pdf",
    )
    assert first.scientific_payload() == second.scientific_payload()


def test_no_generation_docking_or_esol_symbols_in_runner() -> None:
    source = Path("scripts/run_moldisc_015.py").read_text(encoding="utf-8")
    assert "run_moldisc_014" not in source
    assert "vina" not in source.casefold()
