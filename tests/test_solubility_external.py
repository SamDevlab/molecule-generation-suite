from __future__ import annotations

from research_os.benchmark.solubility import SolubilityRecord
from research_os.benchmark.solubility_external import (
    AqSolDBRecord,
    curate_external_records,
    parse_aqsoldb_csv,
)


def test_parse_aqsoldb_records_invalid_rows_without_imputation():
    text = "\n".join(
        [
            "ID,SMILES,Solubility,InChIKey",
            "A1,CCO,-1.25,LFQSCWFLJHTTHZ-UHFFFAOYSA-N",
            "A2,,2.0,",
            "A3,CCN,not-a-number,",
            "A4,CCC,nan,",
        ]
    )
    records, audit = parse_aqsoldb_csv(text)
    assert len(records) == 1
    assert records[0].source_id == "A1"
    assert records[0].measured_log_s_mol_l == -1.25
    assert audit.source_row_count == 4
    assert audit.parsed_record_count == 1
    assert audit.missing_structure_rows == 1
    assert audit.invalid_target_rows == 2
    assert len(audit.parsed_source_hash) == 64


def test_external_curation_excludes_esol_overlap_conflicts_and_invalid_structures():
    esol = (SolubilityRecord("esol-1", "CCO", -1.0),)
    external = (
        AqSolDBRecord("overlap", "OCC", -1.1),
        AqSolDBRecord("same-1", "CCN", -0.5),
        AqSolDBRecord("same-2", "NCC", -0.5),
        AqSolDBRecord("conflict-1", "CCC", -1.0),
        AqSolDBRecord("conflict-2", "C(C)C", -2.0),
        AqSolDBRecord("keep", "CCCl", -1.4),
        AqSolDBRecord("invalid", "not-a-smiles", -3.0),
    )

    retained, audit = curate_external_records(esol, external)
    assert {record.compound_id for record in retained} == {"same-1", "keep"}
    assert audit.invalid_structure_records == 1
    assert audit.overlap_groups_excluded == 1
    assert audit.overlap_records_excluded == 1
    assert audit.conflicting_groups_excluded == 1
    assert audit.conflicting_records_excluded == 2
    assert audit.same_target_duplicate_groups_collapsed == 1
    assert audit.redundant_same_target_records_collapsed == 1
    assert audit.retained_record_count == 2
    assert len(audit.lineage_hash) == 64
    assert len(audit.retained_dataset_hash) == 64


def test_external_curation_lineage_is_order_independent():
    esol = (SolubilityRecord("esol-1", "CCO", -1.0),)
    external = (
        AqSolDBRecord("b", "CCN", -0.5),
        AqSolDBRecord("a", "NCC", -0.5),
        AqSolDBRecord("c", "CCCl", -1.4),
    )
    retained_a, audit_a = curate_external_records(esol, external)
    retained_b, audit_b = curate_external_records(esol, tuple(reversed(external)))
    assert retained_a == retained_b
    assert audit_a.lineage_hash == audit_b.lineage_hash
    assert audit_a.retained_dataset_hash == audit_b.retained_dataset_hash
