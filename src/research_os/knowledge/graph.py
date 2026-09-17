"""Small explicit knowledge graph; edges carry no inferred provenance."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable


RELATIONS = {"supports", "uses", "produces", "describes", "relates_to", "derived_from", "trained_on"}


@dataclass(frozen=True)
class KnowledgeEdge:
    source: str
    relation: str
    target: str
    source_id: str | None = None
    locator: str | None = None

    def __post_init__(self) -> None:
        if self.relation not in RELATIONS:
            raise ValueError(f"unsupported knowledge relation: {self.relation}")

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class KnowledgeGraph:
    edges: list[KnowledgeEdge] = field(default_factory=list)

    def add(self, edge: KnowledgeEdge) -> KnowledgeEdge:
        if edge not in self.edges:
            self.edges.append(edge)
        return edge

    def connect(self, source: str, relation: str, target: str, *, source_id: str | None = None, locator: str | None = None) -> KnowledgeEdge:
        return self.add(KnowledgeEdge(source, relation, target, source_id, locator))

    def outgoing(self, node: str, relation: str | None = None) -> tuple[KnowledgeEdge, ...]:
        return tuple(edge for edge in self.edges if edge.source == node and (relation is None or edge.relation == relation))

    def incoming(self, node: str, relation: str | None = None) -> tuple[KnowledgeEdge, ...]:
        return tuple(edge for edge in self.edges if edge.target == node and (relation is None or edge.relation == relation))

    def to_dict(self) -> dict[str, Any]:
        return {"edges": [edge.to_dict() for edge in self.edges]}

