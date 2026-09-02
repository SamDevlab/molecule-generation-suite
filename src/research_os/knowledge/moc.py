from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Iterable

from research_os.core.hashing import sha256_json
from research_os.core.types import GateResult, GateStatus
from research_os.knowledge.zettel import ReviewStatus


@dataclass(frozen=True)
class MOC:
    moc_id: str
    title: str
    domain: str
    description: str
    zettel_ids: tuple[str, ...] = ()
    child_mocs: tuple[str, ...] = ()
    tags: tuple[str, ...] = ()
    review_status: ReviewStatus = ReviewStatus.REVIEW_REQUIRED

    def __post_init__(self) -> None:
        object.__setattr__(self, "review_status", self.review_status if isinstance(self.review_status, ReviewStatus) else ReviewStatus(str(self.review_status)))
        object.__setattr__(self, "zettel_ids", tuple(str(value) for value in self.zettel_ids))
        object.__setattr__(self, "child_mocs", tuple(str(value) for value in self.child_mocs))
        object.__setattr__(self, "tags", tuple(str(value) for value in self.tags))
        if not self.moc_id.strip() or not self.title.strip() or not self.domain.strip():
            raise ValueError("MOC requires moc_id, title and domain")

    @property
    def digest(self) -> str:
        return sha256_json(self._payload())

    def _payload(self) -> dict[str, Any]:
        data = asdict(self)
        data["review_status"] = self.review_status.value
        data["zettel_ids"] = list(self.zettel_ids)
        data["child_mocs"] = list(self.child_mocs)
        data["tags"] = list(self.tags)
        return data

    def to_dict(self) -> dict[str, Any]:
        data = self._payload()
        data["digest"] = self.digest
        return data


def moc_integrity_gate(moc: MOC, *, known_zettel_ids: Iterable[str], known_moc_ids: Iterable[str] = ()) -> GateResult:
    known_zettels = set(known_zettel_ids)
    known_mocs = set(known_moc_ids)
    missing_zettels = sorted(set(moc.zettel_ids) - known_zettels)
    missing_mocs = sorted(set(moc.child_mocs) - known_mocs)
    if missing_zettels or missing_mocs:
        return GateResult("GATE-KNOW-MOC", "KNOW-MOC-001", GateStatus.INDETERMINATE, "MOC contains unresolved navigation references", diagnostics={"missing_zettel_ids": missing_zettels, "missing_moc_ids": missing_mocs})
    return GateResult("GATE-KNOW-MOC", "KNOW-MOC-001", GateStatus.PASS, "MOC navigation references resolve")


@dataclass
class MOCRegistry:
    _mocs: dict[str, MOC] = field(default_factory=dict)

    def register(self, moc: MOC) -> MOC:
        if moc.moc_id in self._mocs:
            raise ValueError(f"MOC already registered: {moc.moc_id}")
        self._mocs[moc.moc_id] = moc
        return moc

    def get(self, moc_id: str) -> MOC:
        return self._mocs[moc_id]

    def list(self) -> tuple[MOC, ...]:
        return tuple(self._mocs.values())

    def validate(self, moc: MOC, *, known_zettel_ids: Iterable[str]) -> GateResult:
        return moc_integrity_gate(moc, known_zettel_ids=known_zettel_ids, known_moc_ids=self._mocs)
