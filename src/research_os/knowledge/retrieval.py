"""Citation-preserving SQLite FTS retrieval for reviewed knowledge atoms."""

from __future__ import annotations

from dataclasses import dataclass
import sqlite3
from typing import Any, Iterable

from research_os.knowledge.zettel import Zettel


@dataclass(frozen=True)
class RetrievalResult:
    source_id: str
    locator: str | None
    review_status: str
    zettel_id: str
    score: float
    title: str
    summary: str

    def to_dict(self) -> dict[str, Any]:
        return {"source_id": self.source_id, "locator": self.locator, "review_status": self.review_status, "zettel_id": self.zettel_id, "score": self.score, "title": self.title, "summary": self.summary}


class KnowledgeRetriever:
    """Uses SQLite FTS5 when available and returns only indexed source links."""

    def __init__(self, connection: sqlite3.Connection | None = None):
        self.connection = connection or sqlite3.connect(":memory:")
        try:
            self.connection.execute("CREATE VIRTUAL TABLE IF NOT EXISTS zettel_fts USING fts5(zettel_id UNINDEXED, title, summary, source_id UNINDEXED, locator UNINDEXED, review_status UNINDEXED)")
        except sqlite3.OperationalError as exc:
            raise RuntimeError("SQLite FTS5 is required for KnowledgeRetriever") from exc

    def index(self, zettel: Zettel) -> None:
        self.connection.execute("DELETE FROM zettel_fts WHERE zettel_id = ?", (zettel.zettel_id,))
        for source in zettel.sources:
            self.connection.execute("INSERT INTO zettel_fts(zettel_id,title,summary,source_id,locator,review_status) VALUES(?,?,?,?,?,?)", (zettel.zettel_id, zettel.title, zettel.summary, source.source_id, source.section or source.page or source.url, zettel.review_status.value))
        self.connection.commit()

    def index_many(self, zettels: Iterable[Zettel]) -> None:
        for zettel in zettels:
            self.index(zettel)

    def search(self, query: str, *, limit: int = 20, include_rejected: bool = False) -> tuple[RetrievalResult, ...]:
        if not query.strip() or limit <= 0:
            return ()
        sql = "SELECT zettel_id, title, summary, source_id, locator, review_status, bm25(zettel_fts) FROM zettel_fts WHERE zettel_fts MATCH ?"
        params: list[Any] = [query]
        if not include_rejected:
            sql += " AND review_status != ?"
            params.append("REJECTED")
        sql += " ORDER BY bm25(zettel_fts) LIMIT ?"
        params.append(limit)
        rows = self.connection.execute(sql, params).fetchall()
        return tuple(RetrievalResult(row[3], row[4], row[5], row[0], float(row[6]), row[1], row[2]) for row in rows)

