import pytest

from research_os.knowledge import (
    ClaimRecord,
    EvidenceLink,
    KnowledgeBundle,
    NoteRecord,
    SourceRecord,
    bundle_from_json,
    bundle_to_json,
)


def _bundle() -> KnowledgeBundle:
    source = SourceRecord(
        source_id="SRC-SEELIGER-2010",
        kind="paper",
        title="Conformational Transitions upon Ligand Binding: Holo-Structure Prediction from Apo Conformations",
        authors=("Daniel Seeliger", "Bert L. de Groot"),
        year=2010,
        doi="10.1371/journal.pcbi.1000634",
        url="https://doi.org/10.1371/journal.pcbi.1000634",
        license="CC BY",
    )
    note = NoteRecord(
        note_id="NOTE-APODOCK-COHORT",
        source_id=source.source_id,
        locator="Abstract; Table 1",
        summary="The study evaluates ten apo/holo systems spanning large receptor conformational changes, up to 7.1 Å backbone RMSD.",
        tags=("apo-holo", "receptor-flexibility", "benchmark"),
    )
    claim = ClaimRecord(
        claim_id="CLAIM-APODOCK-LARGE-MOTION",
        statement="APODOCK-001 is intentionally a large receptor-motion stress test rather than a routine cognate redocking benchmark.",
        status="SUPPORTED",
        note_ids=(note.note_id,),
        scope="APODOCK-001 cohort rationale",
    )
    evidence = EvidenceLink(
        evidence_id="EVIDENCE-APODOCK-PREFLIGHT",
        claim_id=claim.claim_id,
        benchmark_id="APODOCK-001",
        protocol_id="research-os.apodocking.rigid-known-site.v1.0",
        scientific_result_hash="c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805",
        notes="Prospective structural preflight only; no APODOCK Vina outcome.",
    )
    return KnowledgeBundle([source], [note], [claim], [evidence])


def test_bundle_identity_is_deterministic_and_order_independent():
    bundle = _bundle()
    first = bundle.scientific_identity
    second = _bundle().scientific_identity
    assert first == second
    assert len(first) == 64


def test_json_roundtrip_preserves_scientific_identity():
    original = _bundle()
    restored = bundle_from_json(bundle_to_json(original))
    assert restored.scientific_identity == original.scientific_identity
    assert restored.to_dict() == original.to_dict()


def test_non_hypothesis_claim_requires_source_note():
    claim = ClaimRecord("C1", "A factual claim", "SUPPORTED")
    with pytest.raises(ValueError, match="Sem fonte, sem fato"):
        claim.validate()


def test_hypothesis_may_exist_without_source_note():
    ClaimRecord("H1", "This mechanism may improve ranking.", "HYPOTHESIS").validate()


def test_note_requires_exact_source_locator():
    note = NoteRecord("N1", "S1", "", "Summary")
    with pytest.raises(ValueError, match="exact locator"):
        note.validate()


def test_bundle_fails_on_unknown_references():
    bundle = KnowledgeBundle(
        sources=[SourceRecord("S1", "paper", "Paper", doi="10.1/example")],
        notes=[NoteRecord("N1", "S2", "p. 1", "Summary")],
    )
    with pytest.raises(ValueError, match="unknown source"):
        bundle.validate()


def test_evidence_requires_scientific_identity():
    link = EvidenceLink("E1", "C1", "B1", "P1", "")
    with pytest.raises(ValueError, match="scientific result identity"):
        link.validate()


def test_schema_is_fail_closed():
    with pytest.raises(ValueError, match="unsupported knowledge schema"):
        bundle_from_json('{"schema":"research-os.knowledge.v999"}')
