from pathlib import Path

from research_os.core.hashing import sha256_file
from research_os.external_research import ExternalResearchIntake
from research_os.structure.mmcif import MmcifParseStatus, parse_mmcif


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "real_use_001" / "cox2"


def _registered(tmp_path, filename, source_id):
    path = FIXTURE_DIR / filename
    intake = ExternalResearchIntake(tmp_path / "intake")
    intake.register(source_id=source_id, title=filename, uri=f"https://files.rcsb.org/download/{filename}", local_path=path, expected_sha256=sha256_file(path), provenance={"database": "RCSB PDB", "entry": path.stem})
    return path, intake


def test_mmcif_parser_normalizes_5kir_and_fails_closed_on_ambiguous_ligand(tmp_path):
    path, intake = _registered(tmp_path, "5KIR.cif", "SRC-RCSB-5KIR")
    result = parse_mmcif(path, source_id="SRC-RCSB-5KIR", source_registry=intake.source_registry, require_registered_source=True)
    structure = result.require_valid()
    assert result.status == MmcifParseStatus.VALID
    assert structure.entry_id == "5KIR"
    assert structure.source_sha256 == sha256_file(path)
    assert "RCX" in structure.ligand_components
    assert structure.select_ligand("RCX", chain_id="A").atom_count == 22
    try:
        structure.select_ligand("RCX")
    except ValueError as exc:
        assert "AMBIGUOUS_LIGAND_INSTANCE" in str(exc)
    else:
        raise AssertionError("ambiguous ligand instance was accepted")


def test_mmcif_parser_reads_5ikr_and_rejects_unregistered_source(tmp_path):
    path, intake = _registered(tmp_path, "5IKR.cif", "SRC-RCSB-5IKR")
    result = parse_mmcif(path, source_id="SRC-RCSB-5IKR", source_registry=intake.source_registry, require_registered_source=True)
    assert result.valid
    assert result.require_valid().entry_id == "5IKR"
    blocked = parse_mmcif(path, source_id="SRC-UNKNOWN", source_registry=intake.source_registry, require_registered_source=True)
    assert blocked.status == MmcifParseStatus.SOURCE_NOT_REGISTERED


def test_mmcif_parser_rejects_malformed_and_hash_changed_artifact(tmp_path):
    malformed = tmp_path / "bad.cif"
    malformed.write_text("data_bad\nloop_\n_atom_site.id\n", encoding="utf-8")
    result = parse_mmcif(malformed)
    assert result.status == MmcifParseStatus.INVALID
    source, intake = _registered(tmp_path, "5KIR.cif", "SRC-RCSB-5KIR")
    changed = tmp_path / "changed.cif"
    changed.write_bytes(source.read_bytes() + b"\n# changed\n")
    result = parse_mmcif(changed, source_id="SRC-RCSB-5KIR", source_registry=intake.source_registry, require_registered_source=True)
    assert result.error_code == "SOURCE_HASH_MISMATCH"
