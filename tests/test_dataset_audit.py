import csv

from research_os.molecule.dataset_audit import audit_legacy_csv


def test_streaming_legacy_dataset_audit(tmp_path):
    path = tmp_path / "legacy.csv"
    with path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=["ID", "SMILES", "Peso_Molar", "TPSA"])
        writer.writeheader()
        writer.writerow({"ID": "ethanol", "SMILES": "CCO", "Peso_Molar": 46.069, "TPSA": 20.23})
        writer.writerow({"ID": "bad", "SMILES": "C1(CC", "Peso_Molar": 0, "TPSA": 0})
    report = audit_legacy_csv(path, limit=None)
    assert report.rows_seen == 2
    assert report.rows_with_valid_structure == 1
    assert report.invalid_structures == 1
    assert report.compared_columns["Peso_Molar"].max_absolute_difference < 0.02
    assert len(report.dataset_hash) == 64
