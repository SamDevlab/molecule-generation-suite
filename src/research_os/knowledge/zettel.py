from __future__ import annotations
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
import json,re,uuid
from research_os.core.hashing import sha256_json
from research_os.core.types import EvidenceLevel
class ZettelType(str,Enum):
    CONCEPT="concept"; PRINCIPLE="principle"; EQUATION="equation"; MATERIAL="material"; PROCESS="process"; OBSERVATION="observation"; METHOD="method"; LIMITATION="limitation"; MOC="moc"
class ReviewStatus(str,Enum):
    AUTO_GENERATED="AUTO_GENERATED"; REVIEW_REQUIRED="REVIEW_REQUIRED"; VERIFIED="VERIFIED"; REJECTED="REJECTED"
@dataclass(frozen=True)
class SourceLocator:
    source_id:str; chapter:str|None=None; page:str|None=None; section:str|None=None; doi:str|None=None; url:str|None=None


@dataclass(frozen=True)
class Source:
    """Bibliographic/provenance record; a locator alone is not a full source."""

    source_id: str
    title: str
    authors: tuple[str, ...] = ()
    year: int | None = None
    edition: str | None = None
    doi: str | None = None
    isbn: str | None = None
    license: str | None = None
    status: str | None = None
    locator: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["authors"] = list(self.authors)
        return data
@dataclass(frozen=True)
class Zettel:
    title:str; summary:str; zettel_type:ZettelType; domain:str; evidence_level:EvidenceLevel; review_status:ReviewStatus=ReviewStatus.REVIEW_REQUIRED
    zettel_id:str=field(default_factory=lambda:f"ZTL-{uuid.uuid4().hex[:12].upper()}"); mechanism:str|None=None; equation:str|None=None; conditions:dict[str,Any]=field(default_factory=dict); limitations:tuple[str,...]=(); tags:tuple[str,...]=(); links:tuple[str,...]=(); sources:tuple[SourceLocator,...]=(); created_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat())
    def to_dict(self):
        d=asdict(self); d["zettel_type"]=self.zettel_type.value; d["evidence_level"]=self.evidence_level.value; d["review_status"]=self.review_status.value; return d
    @property
    def digest(self): return sha256_json(self.to_dict())
    def to_markdown(self):
        front={"id":self.zettel_id,"type":self.zettel_type.value,"domain":self.domain,"evidence_level":self.evidence_level.value,"review_status":self.review_status.value,"tags":list(self.tags),"links":list(self.links),"digest":self.digest}; lines=["---",*[f"{k}: {json.dumps(v,ensure_ascii=False)}" for k,v in front.items()],"---","",f"# {self.title}","",self.summary.strip(),""]
        if self.mechanism: lines += ["## Mechanism","",self.mechanism,""]
        if self.equation: lines += ["## Equation","",self.equation,""]
        if self.conditions: lines += ["## Conditions","",json.dumps(self.conditions,ensure_ascii=False,indent=2),""]
        if self.limitations: lines += ["## Limitations","",*[f"- {x}" for x in self.limitations],""]
        if self.sources: lines += ["## Sources","",*[f"- source_id={s.source_id}, chapter={s.chapter}, page={s.page}, doi={s.doi}" for s in self.sources],""]
        if self.links: lines += ["## Connections","",*[f"- [[{x}]]" for x in self.links],""]
        return "\n".join(lines).rstrip()+"\n"
def safe_filename(zettel:Zettel):
    slug=re.sub(r"[^a-zA-Z0-9._-]+","-",zettel.title.strip()).strip("-")[:80] or "note"; return f"{zettel.zettel_id}_{slug}.md"
def write_zettel(zettel:Zettel,directory:str|Path):
    target=Path(directory); target.mkdir(parents=True,exist_ok=True); path=target/safe_filename(zettel); path.write_text(zettel.to_markdown(),encoding="utf-8"); return path
