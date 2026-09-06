from pathlib import Path

from research_os.external_research import ExternalResearchIntake, SourceAvailabilityCode, SourceState
from research_os.core.hashing import sha256_file


FIXTURE = Path(__file__).parent / "fixtures" / "real_use_001" / "cox2" / "5KIR.cif"


def test_external_intake_registers_real_artifact_and_is_idempotent(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    digest = sha256_file(FIXTURE)
    first = intake.register(source_id="SRC-RCSB-5KIR", title="RCSB 5KIR mmCIF", uri="https://files.rcsb.org/download/5KIR.cif", local_path=FIXTURE, expected_sha256=digest, provenance={"database": "RCSB PDB", "locator": "5KIR"})
    second = intake.register(source_id="SRC-RCSB-5KIR", title="RCSB 5KIR mmCIF", uri="https://files.rcsb.org/download/5KIR.cif", local_path=FIXTURE, expected_sha256=digest, provenance={"database": "RCSB PDB", "locator": "5KIR"})
    assert first.state == SourceState.SOURCE_VALID
    assert first.availability.code == SourceAvailabilityCode.LOCAL_ARTIFACT_VALID
    assert first.source_fingerprint == second.source_fingerprint
    assert first.digest == second.digest
    assert intake.source_registry.verify_document("SRC-RCSB-5KIR", FIXTURE)


def test_external_intake_rejects_hash_mismatch_and_missing_artifact(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    provenance = {"database": "example", "locator": "bad"}
    bad = intake.register(source_id="SRC-BAD", title="bad", uri="https://example.invalid/bad.cif", local_path=FIXTURE, expected_sha256="0" * 64, provenance=provenance)
    missing = intake.register(source_id="SRC-MISSING", title="missing", uri="https://example.invalid/missing.cif", local_path=tmp_path / "missing.cif", provenance=provenance)
    assert bad.state == SourceState.SOURCE_INVALID
    assert bad.availability.code == SourceAvailabilityCode.ARTIFACT_HASH_MISMATCH
    assert missing.state == SourceState.SOURCE_UNAVAILABLE
    assert missing.availability.code == SourceAvailabilityCode.LOCAL_ARTIFACT_MISSING


def test_external_intake_preserves_remote_unavailability_and_comparability(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    intake.register(source_id="SRC-REMOTE", title="remote", uri="https://example.invalid/source", provenance={"database": "example", "locator": "source"})
    denied = intake.assess_remote("SRC-REMOTE", http_status=403)
    incomparable = intake.assess_remote("SRC-REMOTE", comparable=False)
    assert denied.availability.code == SourceAvailabilityCode.HTTP_403
    assert denied.state == SourceState.SOURCE_UNAVAILABLE
    assert incomparable.availability.code == SourceAvailabilityCode.NOT_COMPARABLE
    assert incomparable.state == SourceState.SOURCE_NOT_COMPARABLE


def test_valid_local_cache_remains_usable_when_remote_source_returns_403(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    digest = sha256_file(FIXTURE)
    intake.register(source_id="SRC-CACHED", title="cached", uri="https://example.invalid/cached", local_path=FIXTURE, expected_sha256=digest, provenance={"database": "example", "locator": "cached"})
    result = intake.assess_remote("SRC-CACHED", http_status=403)
    assert result.state == SourceState.SOURCE_VALID
    assert result.availability.code == SourceAvailabilityCode.HTTP_403
    assert "local artifact remains hash-valid" in result.availability.detail


def test_external_intake_marks_identity_change_without_overwriting_registry(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    intake.register(source_id="SRC-CHANGE", title="source", uri="https://example.invalid/source", provenance={"database": "example", "locator": "source"})
    changed = intake.register(source_id="SRC-CHANGE", title="source changed", uri="https://example.invalid/source", provenance={"database": "example", "locator": "source"})
    assert changed.state == SourceState.SOURCE_CHANGED
    assert changed.availability.code == SourceAvailabilityCode.INVALID_RESPONSE
    assert intake.source_registry.get("SRC-CHANGE").title == "source"


def test_external_campaign_requires_registered_hash_valid_sources(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    digest = sha256_file(FIXTURE)
    intake.register(source_id="SRC-CAMPAIGN", title="RCSB 5KIR", uri="https://files.rcsb.org/download/5KIR.cif", local_path=FIXTURE, expected_sha256=digest, source_revision="2.3", provenance={"database": "RCSB PDB", "locator": "5KIR"})
    campaign = intake.register_campaign(campaign_id="CAM-001", research_question="cross-structure pose recovery", primary_question="Can the declared protocol be reproduced?", secondary_questions=("Is the ligand identity stable?",), declared_protocol={"protocol_id": "real-use-001.v1", "model": 1}, source_ids=("SRC-CAMPAIGN",), parser_normalizer_version="gemmi-0.7.5/research-os-mmcif.v1", expected_capability=("mmcif", "pose-recovery"), reproducibility_metadata={"seed": 42})
    replay = intake.register_campaign(campaign_id="CAM-001", research_question="cross-structure pose recovery", primary_question="Can the declared protocol be reproduced?", secondary_questions=("Is the ligand identity stable?",), declared_protocol={"protocol_id": "real-use-001.v1", "model": 1}, source_ids=("SRC-CAMPAIGN",), parser_normalizer_version="gemmi-0.7.5/research-os-mmcif.v1", expected_capability=("mmcif", "pose-recovery"), reproducibility_metadata={"seed": 42})
    restored = ExternalResearchIntake(tmp_path / "intake")
    assert campaign.valid and replay.digest == campaign.digest and restored.get_campaign("CAM-001").digest == campaign.digest
    assert campaign.input_validation_state.value == "UNVALIDATED"


def test_external_source_requires_complete_provenance_and_uri(tmp_path):
    intake = ExternalResearchIntake(tmp_path / "intake")
    try:
        intake.register(source_id="SRC-NO-PROV", title="source", uri="https://example.invalid/source")
    except ValueError as exc:
        assert "provenance" in str(exc)
    else:
        raise AssertionError("incomplete provenance was accepted")
    try:
        intake.register(source_id="SRC-NO-URI", title="source", uri="", provenance={"database": "example", "locator": "source"})
    except ValueError:
        pass
    else:
        raise AssertionError("empty URI was accepted")
