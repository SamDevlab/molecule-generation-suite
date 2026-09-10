from __future__ import annotations

import json
from pathlib import Path

import pytest

from research_os.cli import main
from research_os.legacy_runtime import biolab_preflight, require_executable, resolve_executable


ROOT = Path(__file__).resolve().parents[1]


def _make_executable(path: Path) -> Path:
    path.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    path.chmod(path.stat().st_mode | 0o111)
    return path


def test_executable_resolution_prefers_explicit_environment(tmp_path: Path):
    executable = _make_executable(tmp_path / "vina")
    result = resolve_executable(
        "vina",
        env_var="RESEARCH_OS_VINA",
        path_candidates=("vina",),
        environment={"RESEARCH_OS_VINA": str(executable)},
    )
    assert result.available is True
    assert result.source == "env:RESEARCH_OS_VINA"
    assert result.path == str(executable.resolve())


def test_invalid_explicit_override_fails_closed_without_path_fallback(monkeypatch, tmp_path: Path):
    fallback = _make_executable(tmp_path / "fallback-vina")
    monkeypatch.setattr("research_os.legacy_runtime.shutil.which", lambda _: str(fallback))
    result = resolve_executable(
        "vina",
        env_var="RESEARCH_OS_VINA",
        path_candidates=("vina",),
        environment={"RESEARCH_OS_VINA": str(tmp_path / "missing-vina")},
    )
    assert result.available is False
    assert result.source == "env:RESEARCH_OS_VINA"
    with pytest.raises(FileNotFoundError):
        require_executable(result)


def test_biolab_preflight_reports_first_loss_when_engines_are_missing(monkeypatch, tmp_path: Path):
    monkeypatch.setattr("research_os.legacy_runtime.shutil.which", lambda _: None)
    result = biolab_preflight(tmp_path, environment={})
    assert result["status"] == "INDETERMINATE"
    assert result["first_loss"] == "MISSING_EXTERNAL_EXECUTABLE"
    assert result["missing"] == ["vina", "obabel"]


def test_biolab_preflight_passes_with_explicit_engines(tmp_path: Path):
    vina = _make_executable(tmp_path / "vina")
    obabel = _make_executable(tmp_path / "obabel")
    result = biolab_preflight(
        tmp_path,
        environment={
            "RESEARCH_OS_VINA": str(vina),
            "RESEARCH_OS_OBABEL": str(obabel),
        },
    )
    assert result["status"] == "PASS"
    assert result["first_loss"] is None


def test_cli_legacy_preflight_is_fail_closed(monkeypatch, tmp_path: Path, capsys):
    monkeypatch.setattr("research_os.legacy_runtime.shutil.which", lambda _: None)
    monkeypatch.delenv("RESEARCH_OS_VINA", raising=False)
    monkeypatch.delenv("RESEARCH_OS_OBABEL", raising=False)
    assert main(["legacy-preflight", str(tmp_path)]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "INDETERMINATE"
    assert payload["first_loss"] == "MISSING_EXTERNAL_EXECUTABLE"


def test_qed_legacy_script_no_longer_makes_clinical_confidence_claims():
    text = (ROOT / "formolecular" / "g_oraculo_farma.py").read_text(encoding="utf-8")
    forbidden = (
        "Confiabilidade Clínica",
        "A IA agora domina a biologia química",
        "Caçar a Cura",
        "VARREDURA CLÍNICA",
        "RELATÓRIO CLÍNICO",
    )
    for phrase in forbidden:
        assert phrase not in text
    assert "scaffold_group_holdout" in text
    assert "QED_Direct_RDKit" in text
    assert "surrogate-model metrics only; not clinical confidence" in text


def test_legacy_directories_declare_audit_only_boundary():
    biolab = (ROOT / "Biolab" / "README.md").read_text(encoding="utf-8")
    formolecular = (ROOT / "formolecular" / "README.md").read_text(encoding="utf-8")
    assert "legacy exploratory workflows" in biolab
    assert "legacy exploratory workflows" in formolecular
    assert "canonical execution layer" in biolab.lower()
    assert "exploratory/audit-only code" in biolab.lower()
    assert "not as the current scientific source of truth" in formolecular
