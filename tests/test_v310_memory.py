from __future__ import annotations

import pytest

from research_os.memory import MemoryVersion, ResearchMemorySnapshot, TemporalMemoryRecord, TemporalScientificMemory


def test_snapshot_is_digest_valid_and_nested_versions_are_frozen() -> None:
    snapshot = ResearchMemorySnapshot(
        "SNAP-1",
        "2026-09-04T00:00:00+00:00",
        "commit",
        "ledger",
        dataset_versions=(MemoryVersion("dataset", "v1", "2026-09-04T00:00:00+00:00", ("RUN-1",), "CURRENT", True),),
    )
    assert snapshot.valid
    with pytest.raises(Exception):
        snapshot.dataset_versions += ()
    with pytest.raises(Exception):
        snapshot.dataset_versions[0].version = "v2"  # type: ignore[misc]


def test_temporal_query_ignores_conversational_false_memory() -> None:
    memory = TemporalScientificMemory()
    memory.add_record(TemporalMemoryRecord("run:1", "run", "2026-09-04T00:00:00+00:00", "RUN-1", {"subject": "celecoxib COX-2 docking", "status": "SEALED"}, (), None, "SEALED"))
    memory.add_record(TemporalMemoryRecord("decision:1", "decision", "2026-09-04T00:00:00+00:00", "DECISION-1", {"decision_status": "NO_DECISION_OUT_OF_DOMAIN", "evidence_level": "E2_COMPUTATIONAL", "subject": "celecoxib"}, ("RUN-1",), None, "NO_DECISION_OUT_OF_DOMAIN"))
    result = memory.query("Was celecoxib experimentally validated?", conversation_memory=("We already experimentally validated celecoxib.",))
    assert result.grounded
    assert result.conversation_memory_ignored
    assert "no experimental validation" in result.answer.lower()


def test_constraints_are_returned_from_registered_memory() -> None:
    memory = TemporalScientificMemory()
    memory.add_record(TemporalMemoryRecord("constraints", "program_constraints", "2026-09-04T00:00:00+00:00", "v3.9", {"constraints": ["AqSolDB external validation is still absent", "Docking E2 only"]}, (), "3.9.0", "PERSISTED"))
    result = memory.query("Do fresh programs remember AqSolDB and Docking E2 constraints?")
    assert result.grounded
    assert "AqSolDB external validation is still absent" in result.answer
    assert "Docking E2 only" in result.answer
