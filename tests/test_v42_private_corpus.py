from pathlib import Path

import pytest

from research_os.knowledge import (
    CorpusReadinessStatus,
    PrivateConfidentiality,
    PrivateCorpusService,
    PrivateSourceRecord,
    ReviewStatus,
)


def test_private_source_record_persists_hash_and_metadata_only():
    record = PrivateSourceRecord("SRC-PRIVATE-1", "notes.md", "a" * 64, "MARKDOWN", "Lab notes")
    data = record.to_dict()
    assert data["content_hash"] == "a" * 64
    assert data["confidentiality"] == PrivateConfidentiality.PRIVATE_USER_SOURCE.value
    assert "text" not in data and "contents" not in data


def test_empty_corpus_is_explicitly_awaiting_user_corpus():
    assert PrivateCorpusService.readiness_status(()) is CorpusReadinessStatus.INFRASTRUCTURE_READY_AWAITING_USER_CORPUS


def test_ingestion_is_auto_extracted_and_persists_no_private_text(tmp_path: Path):
    service = PrivateCorpusService(tmp_path / "state")
    result = service.ingest_text(
        source_id="SRC-PRIVATE-2",
        filename="private.md",
        title="Private protocol",
        text="# Method\nTemperature = 300 K.\n",
    )
    assert result.source.ingestion_status.value == "AUTO_EXTRACTED"
    assert result.source.review_status is ReviewStatus.REVIEW_REQUIRED
    assert result.review_queue
    persisted = (tmp_path / "state" / "private-sources" / "SRC-PRIVATE-2.json").read_text(encoding="utf-8")
    assert "Temperature = 300 K" not in persisted
    assert result.ingestion is not None
    assert all(item.status.value == "REVIEW_REQUIRED" for item in result.review_queue)


def test_verified_candidate_requires_locator_context_and_clean_extraction(tmp_path: Path):
    service = PrivateCorpusService(tmp_path / "state")
    result = service.ingest_text(source_id="SRC-PRIVATE-3", filename="notes.md", title="Notes", text="# A\nReadable context.")
    with pytest.raises(ValueError, match="locator"):
        service.review(result.source, item_id="CLAIM-1", item_type="claim", action="VERIFY", locator="", supporting_context="context")
    with pytest.raises(ValueError, match="corrupted"):
        service.review(result.source, item_id="CLAIM-1", item_type="claim", action="VERIFY", locator="section A", supporting_context="context", extraction_corruption=True)
    decision = service.review(result.source, item_id="CLAIM-1", item_type="claim", action="VERIFY", locator="section A", supporting_context="Readable context.")
    assert decision.resulting_review_status is ReviewStatus.VERIFIED


def test_file_ingestion_rejects_path_escape_and_binary_without_adapter(tmp_path: Path):
    root = tmp_path / "corpus"
    root.mkdir()
    (root / "safe.md").write_text("# Safe\nContent.", encoding="utf-8")
    service = PrivateCorpusService()
    with pytest.raises(ValueError, match="inside"):
        service.ingest_file(tmp_path / "outside.md", corpus_root=root, source_id="SRC-OUT")
    (root / "report.pdf").write_bytes(b"%PDF")
    with pytest.raises(ValueError, match="format adapter"):
        service.ingest_file(root / "report.pdf", corpus_root=root, source_id="SRC-PDF")


def test_source_conflict_does_not_choose_private_or_public_source(tmp_path: Path):
    conflict = PrivateCorpusService(tmp_path / "state").record_conflict(
        "SRC-PRIVATE", "SRC-PUBLIC", ("temperature", "processing"), ("protocols require review",)
    )
    assert conflict.status == "REVIEW_REQUIRED"
    assert conflict.source_id_a == "SRC-PRIVATE"
    assert conflict.source_id_b == "SRC-PUBLIC"
