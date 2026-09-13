from __future__ import annotations

from pathlib import Path
import subprocess

from rdkit import Chem
from rdkit.Chem import AllChem
import pytest

from research_os.docking.apodock001_raw_coordinate_adapter import (
    ADAPTER_ID,
    DIAGNOSTIC_STATUS,
    RawCoordinateAdapterError,
    evaluate_raw_pdbqt,
    parse_raw_pdbqt,
)


def _molecule() -> Chem.Mol:
    molecule = Chem.AddHs(Chem.MolFromSmiles("CCO"))
    assert AllChem.EmbedMolecule(molecule, randomSeed=42) == 0
    return molecule


def _atom_line(serial: int, symbol: str, x: float, y: float, z: float) -> str:
    atom_type = {"C": "C", "O": "OA", "H": "HD"}[symbol]
    return (
        f"ATOM  {serial:5d} {symbol:>4} UNL     1    "
        f"{x:8.3f}{y:8.3f}{z:8.3f}  0.00  0.00    0.000 {atom_type:>2}\n"
    )


def _write_template(path: Path, molecule: Chem.Mol) -> None:
    writer = Chem.SDWriter(str(path))
    writer.write(Chem.RemoveHs(molecule))
    writer.close()


def _write_raw(path: Path, molecule: Chem.Mol, *, translation: tuple[float, float, float] = (0, 0, 0)) -> None:
    conformer = molecule.GetConformer()
    lines = ["MODEL        1\n", "REMARK VINA RESULT:      -5.000      0.000      0.000\n"]
    serial = 1
    for atom in molecule.GetAtoms():
        if atom.GetAtomicNum() == 1:
            continue
        point = conformer.GetAtomPosition(atom.GetIdx())
        lines.append(
            _atom_line(
                serial,
                atom.GetSymbol(),
                point.x + translation[0],
                point.y + translation[1],
                point.z + translation[2],
            )
        )
        serial += 1
    lines.append("ENDMDL\n")
    path.write_text("".join(lines), encoding="utf-8", newline="")


def test_raw_coordinate_adapter_preserves_same_frame_translation(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    molecule = _molecule()
    template = tmp_path / "template.sdf"
    raw = tmp_path / "raw.pdbqt"
    _write_template(template, molecule)
    _write_raw(raw, molecule, translation=(5.0, 0.0, 0.0))
    before = raw.read_bytes()

    def forbidden_subprocess(*args, **kwargs):
        raise AssertionError("postmortem raw-coordinate adapter must not invoke subprocess")

    monkeypatch.setattr(subprocess, "run", forbidden_subprocess)
    results = evaluate_raw_pdbqt(raw, molecule, template)

    assert ADAPTER_ID.startswith("research-os.apodock001.postmortem.raw-coordinate-adapter.v1+")
    assert results[0].to_dict()["status"] == DIAGNOSTIC_STATUS
    assert results[0].rmsd.status == "PASS"
    assert results[0].rmsd.rmsd_angstrom == pytest.approx(5.0, abs=0.002)
    assert raw.read_bytes() == before


def test_raw_parser_preserves_vina_order_and_score(tmp_path: Path) -> None:
    molecule = _molecule()
    raw = tmp_path / "raw.pdbqt"
    _write_raw(raw, molecule)
    poses = parse_raw_pdbqt(raw)
    assert [pose.pose_index for pose in poses] == [1]
    assert poses[0].score_kcal_mol == -5.0
    assert [atom.serial for atom in poses[0].atoms] == [1, 2, 3]


def test_template_identity_mismatch_fails_closed(tmp_path: Path) -> None:
    molecule = _molecule()
    other = Chem.AddHs(Chem.MolFromSmiles("CCN"))
    assert AllChem.EmbedMolecule(other, randomSeed=42) == 0
    template = tmp_path / "template.sdf"
    raw = tmp_path / "raw.pdbqt"
    _write_template(template, other)
    _write_raw(raw, molecule)
    with pytest.raises(RawCoordinateAdapterError, match="template/raw atom identity differs"):
        evaluate_raw_pdbqt(raw, molecule, template)
