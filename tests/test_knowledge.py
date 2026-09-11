import pytest

from research_os.core.types import EvidenceLevel
from research_os.knowledge import (
    BenchmarkKnowledgeLink,
    ReviewStatus,
    SourceLocator,
    SourceRecord,
    SourceType,
    Zettel,
    ZettelType,
    benchmark_knowledge_identity,
    bundle_from_mapping,
    validate_benchmark_knowledge_link,
)


def _records(*, retrieved_at="2026-09-11T00:00:00+00:00", created_at="2026-09-11T00:00:00+00:00"):
    source = SourceRecord(
        source_id="SRC-SEELIGER-2010",
        title="Conformational Transitions upon Ligand Binding: Holo-Structure Prediction from Apo Conformations",
        authors=("Daniel Seeliger", "Bert L. de Groot"),
        year=2010,
        doi="10.1371/journal.pcbi.1000634",
        url="https://doi.org/10.1371/journal.pcbi.1000634",
        license="CC BY",
        retrieved_at=retrieved_at,
        source_type=SourceType.PAPER,
    )
    zettel = Zettel(
        zettel_id="ZTL-APODOCK-LARGE-MOTION",
        title="APODOCK-001 large receptor-motion cohort",
        summary="The published cohort contains ten apo/holo systems with large receptor conformational changes, reaching 7.1 Å backbone RMSD.",
        zettel_type=ZettelType.METHOD,
        domain="molecular-docking",
        evidence_level=EvidenceLevel.E4_CURATED_EXPERIMENTAL,
        review_status=ReviewStatus.VERIFIED,
        tags=("apo-holo", "receptor-flexibility", "benchmark"),
        sources=(SourceLocator(source.source_id, section="Abstract; Table 1", doi=source.doi),),
        created_at=created_at,
    )
    link = BenchmarkKnowledgeLink(
        link_id="BKL-APODOCK-001-PREFLIGHT",
        benchmark_id="APODOCK-001",
        protocol_id="research-os.apodocking.rigid-known-site.v1.0",
        scientific_result_hash="c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805",
        source_ids=(source.source_id,),
        zettel_ids=(zettel.zettel_id,),
        artifact_id="10279879902",
        boundary="pre-result",
    )
    return source, zettel, link


def test_benchmark_knowledge_identity_ignores_retrieval_timestamps():
    first = _records(retrieved_at="2026-09-11T00:00:00+00:00", created_at="2026-09-11T00:00:00+00:00")
    second = _records(retrieved_at="2026-09-12T00:00:00+00:00", created_at="2026-09-12T00:00:00+00:00")
    assert benchmark_knowledge_identity(sources=[first[0]], zettels=[first[1]], links=[first[2]]) == benchmark_knowledge_identity(sources=[second[0]], zettels=[second[1]], links=[second[2]])


def test_verified_benchmark_note_requires_specific_locator():
    source, zettel, link = _records()
    bad = Zettel(
        zettel_id=zettel.zettel_id,
        title=zettel.title,
        summary=zettel.summary,
        zettel_type=zettel.zettel_type,
        domain=zettel.domain,
        evidence_level=zettel.evidence_level,
        review_status=ReviewStatus.VERIFIED,
        sources=(SourceLocator(source.source_id, doi=source.doi),),
    )
    with pytest.raises(ValueError, match="page/chapter/section"):
        validate_benchmark_knowledge_link(link, sources=[source], zettels=[bad])


def test_benchmark_link_rejects_unreviewed_zettel():
    source, zettel, link = _records()
    pending = Zettel(
        zettel_id=zettel.zettel_id,
        title=zettel.title,
        summary=zettel.summary,
        zettel_type=zettel.zettel_type,
        domain=zettel.domain,
        evidence_level=zettel.evidence_level,
        review_status=ReviewStatus.REVIEW_REQUIRED,
        sources=zettel.sources,
    )
    with pytest.raises(ValueError, match="must be VERIFIED"):
        validate_benchmark_knowledge_link(link, sources=[source], zettels=[pending])


def test_benchmark_link_rejects_unknown_source():
    source, zettel, link = _records()
    with pytest.raises(ValueError, match="unknown source IDs"):
        validate_benchmark_knowledge_link(link, sources=[], zettels=[zettel])


def test_bundle_schema_is_fail_closed():
    with pytest.raises(ValueError, match="unsupported benchmark knowledge schema"):
        bundle_from_mapping({"schema": "research-os.benchmark-knowledge.v999"})


def test_link_requires_sha256_scientific_identity():
    with pytest.raises(ValueError, match="SHA-256"):
        BenchmarkKnowledgeLink(
            link_id="BKL-1",
            benchmark_id="B1",
            protocol_id="P1",
            scientific_result_hash="not-a-hash",
            source_ids=("S1",),
            zettel_ids=("Z1",),
        )
