import sqlite3

import pytest

from research_os.knowledge import (
    EquationDomainError,
    EquationRecord,
    EquationRegistry,
    KnowledgeGraph,
    KnowledgeIngestionPipeline,
    KnowledgeRetriever,
    SourceRecord,
    SourceType,
)
from research_os.knowledge.zettel import ReviewStatus


def test_source_registry_round_trip(tmp_path):
    registry = __import__("research_os.knowledge", fromlist=["SourceRegistry"]).SourceRegistry(tmp_path)
    source = registry.register(SourceRecord("SRC-1", "A paper", authors=("A",), source_type=SourceType.PAPER, doi="10.1/example"))
    assert registry.get("SRC-1").digest == source.digest
    assert registry.list()[0].source_type is SourceType.PAPER


def test_ingestion_only_creates_review_required_atoms():
    result = KnowledgeIngestionPipeline().ingest(SourceRecord("SRC-1", "Manual", source_type=SourceType.MANUAL), "# Combustion\nThe equation is q = m c T.")
    assert result.document.status.value == "AUTO_EXTRACTED"
    assert result.zettels[0].review_status is ReviewStatus.REVIEW_REQUIRED
    assert result.review_queue
    assert all(item.status.value == "REVIEW_REQUIRED" for item in result.review_queue)
    assert result.equations[0].source_id == "SRC-1"


def test_equation_domain_is_fail_closed():
    equation = EquationRecord("EQ-1", "y = x", ("x",), {"x": "1"}, domain={"temperature": {"min": 300, "max": 1000}})
    equation.assert_in_domain({"temperature": 300})
    with pytest.raises(EquationDomainError):
        equation.assert_in_domain({"temperature": 299})


def test_retrieval_returns_source_and_review_metadata():
    source = SourceRecord("SRC-1", "Fuel handbook", url="https://example.invalid/fuel")
    result = KnowledgeIngestionPipeline().ingest(source, "# Fuel\nCombustion conditions matter.")
    retriever = KnowledgeRetriever(sqlite3.connect(":memory:"))
    retriever.index_many(result.zettels)
    hits = retriever.search("conditions")
    assert hits and hits[0].source_id == "SRC-1"
    assert hits[0].review_status == "REVIEW_REQUIRED"
    assert hits[0].zettel_id == result.zettels[0].zettel_id


def test_graph_does_not_accept_unknown_relation():
    graph = KnowledgeGraph()
    graph.connect("SRC-1", "supports", "CLM-1", source_id="SRC-1", locator="p. 1")
    assert graph.incoming("CLM-1")[0].source_id == "SRC-1"
    with pytest.raises(ValueError):
        graph.connect("A", "invented", "B")

