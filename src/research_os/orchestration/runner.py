from __future__ import annotations
from dataclasses import asdict,dataclass,field
from datetime import datetime,timezone
from typing import Any
import uuid
from research_os.core.types import RunManifest
from research_os.orchestration.registry import LabRegistry
@dataclass(frozen=True)
class PlanStep:
    step_id:str; lab:str; inputs:dict[str,Any]; experiment:str="default"; requires:tuple[str,...]=()
@dataclass
class PlanRun:
    plan_id:str=field(default_factory=lambda:f"PLAN-{uuid.uuid4().hex[:12].upper()}"); created_at:str=field(default_factory=lambda:datetime.now(timezone.utc).isoformat()); runs:dict[str,RunManifest]=field(default_factory=dict); skipped:dict[str,str]=field(default_factory=dict)
    @property
    def passed(self): return bool(self.runs) and not self.skipped and all(r.passed for r in self.runs.values())
    def to_dict(self): return asdict(self)
class ResearchOrchestrator:
    """Executes an explicit lab plan; it does not silently invent workflows."""
    def __init__(self,registry:LabRegistry): self.registry=registry
    def run(self,steps:list[PlanStep]):
        p=PlanRun(); ids=[s.step_id for s in steps]
        if len(ids)!=len(set(ids)): raise ValueError("plan step_id values must be unique")
        known=set(ids)
        for s in steps:
            unknown=set(s.requires)-known
            if unknown: raise ValueError(f"step {s.step_id} has unknown dependencies: {sorted(unknown)}")
            unmet=[d for d in s.requires if d not in p.runs or not p.runs[d].passed]
            if unmet: p.skipped[s.step_id]=f"upstream requirements not satisfied: {', '.join(unmet)}"; continue
            p.runs[s.step_id]=self.registry.get(s.lab).run(s.inputs,experiment=s.experiment)
        return p
