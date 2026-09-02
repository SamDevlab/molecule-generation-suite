from __future__ import annotations
from typing import Any
import uuid
from research_os.core.types import Evidence,EvidenceLevel,GateResult,GateStatus,RunManifest
from research_os.knowledge.zettel import ReviewStatus,SourceLocator,Zettel,ZettelType
from research_os.labs.base import Lab
from research_os.proof.engine import ProofEngine
from research_os.proof.rules import Rule,require_fields
class KnowledgeLab(Lab):
    name="KnowledgeLab"
    def normalize(self,raw:dict[str,Any]):
        sources=[{k:s.get(k) for k in ("source_id","chapter","page","section","doi","url")} for s in raw.get("sources") or []]
        return {"title":raw.get("title"),"summary":raw.get("summary"),"zettel_type":str(raw.get("zettel_type","concept")).lower(),"domain":raw.get("domain"),"evidence_level":raw.get("evidence_level",EvidenceLevel.E0_HEURISTIC.value),"review_status":raw.get("review_status",ReviewStatus.REVIEW_REQUIRED.value),"mechanism":raw.get("mechanism"),"equation":raw.get("equation"),"conditions":dict(raw.get("conditions") or {}),"limitations":tuple(raw.get("limitations") or ()),"tags":tuple(raw.get("tags") or ()),"links":tuple(raw.get("links") or ()),"sources":sources}
    def rules(self):
        rules=[require_fields("KNOW-NOTE-001",("title","summary","domain","zettel_type","evidence_level","review_status"))]
        def enums(ctx,evidence):
            invalid={}
            for key,enum in (("zettel_type",ZettelType),("evidence_level",EvidenceLevel),("review_status",ReviewStatus)):
                try: enum(ctx[key])
                except ValueError: invalid[key]=ctx[key]
            return GateResult("GATE-KNOW-SCHEMA","KNOW-NOTE-002",GateStatus.FAIL,"invalid knowledge-note enum values",diagnostics=invalid) if invalid else GateResult("GATE-KNOW-SCHEMA","KNOW-NOTE-002",GateStatus.PASS,"knowledge-note enum values valid")
        def sources(ctx,evidence):
            ss=ctx.get("sources") or []
            if ReviewStatus(ctx["review_status"])==ReviewStatus.VERIFIED and not ss: return GateResult("GATE-KNOW-SOURCE","KNOW-SRC-001",GateStatus.INSUFFICIENT_EVIDENCE,"a VERIFIED knowledge note must retain at least one source locator")
            bad=[i for i,s in enumerate(ss) if not s.get("source_id")]
            return GateResult("GATE-KNOW-SOURCE","KNOW-SRC-001",GateStatus.FAIL,"source locators require source_id",diagnostics={"indices":bad}) if bad else GateResult("GATE-KNOW-SOURCE","KNOW-SRC-001",GateStatus.PASS,"source traceability requirement met")
        rules += [Rule("KNOW-NOTE-002","Validate Zettelkasten enum fields",enums),Rule("KNOW-SRC-001","Require traceable sources for verified notes",sources),Rule("KNOW-REV-001","Record review state without automatic promotion",lambda c,e:GateResult("GATE-KNOW-REVIEW","KNOW-REV-001",GateStatus.PASS,"review state recorded explicitly"))]; return rules
    def run(self,raw:dict[str,Any],experiment:str="zettel_ingestion"):
        n=self.normalize(raw); m=RunManifest(lab=self.name,experiment=experiment,inputs=n); ProofEngine().evaluate(m,self.rules())
        if not m.passed:return m
        z=Zettel(title=n["title"],summary=n["summary"],zettel_type=ZettelType(n["zettel_type"]),domain=n["domain"],evidence_level=EvidenceLevel(n["evidence_level"]),review_status=ReviewStatus(n["review_status"]),mechanism=n["mechanism"],equation=n["equation"],conditions=n["conditions"],limitations=n["limitations"],tags=n["tags"],links=n["links"],sources=tuple(SourceLocator(**s) for s in n["sources"])); m.evidence.append(Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",kind="zettelkasten_note",level=z.evidence_level,source="KnowledgeLab validated Zettel",payload={"zettel":z.to_dict(),"digest":z.digest})); return m
def zettel_to_training_record(z:Zettel):
    return {"id":z.zettel_id,"instruction":f"Explain the concept: {z.title}","response":z.summary,"domain":z.domain,"type":z.zettel_type.value,"conditions":z.conditions,"limitations":list(z.limitations),"links":list(z.links),"sources":[s.__dict__ for s in z.sources],"evidence_level":z.evidence_level.value,"review_status":z.review_status.value,"digest":z.digest}
