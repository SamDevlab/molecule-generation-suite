from pathlib import Path

from research_os.structure.mmcif import MmcifParseStatus, parse_mmcif


ROOT = Path(__file__).parent / "fixtures" / "real_use_001" / "adversarial"


def test_adversarial_mmcif_fixtures_fail_closed_at_the_declared_boundary():
    altloc = parse_mmcif(ROOT / "altloc.cif").require_valid()
    try:
        altloc.select_ligand("LIG")
    except ValueError as exc:
        assert "ALTLOC_UNRESOLVED" in str(exc)
    else:
        raise AssertionError("unresolved altloc was accepted")
    models = parse_mmcif(ROOT / "multiple_models.cif", require_single_model=True)
    assert models.status == MmcifParseStatus.INVALID and models.error_code == "MULTIPLE_MODELS"
    duplicate = parse_mmcif(ROOT / "ligand_duplicate.cif").require_valid()
    try:
        duplicate.select_ligand("LIG")
    except ValueError as exc:
        assert "AMBIGUOUS_LIGAND_INSTANCE" in str(exc)
    else:
        raise AssertionError("duplicate ligand instance was accepted")


def test_adversarial_mmcif_fixtures_reject_missing_or_inconsistent_input():
    missing = parse_mmcif(ROOT / "ligand_missing.cif").require_valid()
    try:
        missing.select_ligand("LIG")
    except ValueError as exc:
        assert "LIGAND_NOT_FOUND" in str(exc)
    else:
        raise AssertionError("missing ligand was accepted")
    coordinates = parse_mmcif(ROOT / "missing_coordinates.cif")
    assert coordinates.status == MmcifParseStatus.INVALID and coordinates.error_code == "MISSING_COORDINATE"
    truncated = parse_mmcif(ROOT / "truncated.cif")
    assert truncated.status == MmcifParseStatus.INVALID
    inconsistent = parse_mmcif(ROOT / "inconsistent_ids.cif").require_valid()
    try:
        inconsistent.select_ligand("LIG")
    except ValueError as exc:
        assert "CHEMICAL_COMPONENT_MISMATCH" in str(exc)
    else:
        raise AssertionError("inconsistent chemical component ID was accepted")
