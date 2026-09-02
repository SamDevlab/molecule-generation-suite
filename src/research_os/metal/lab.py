from __future__ import annotations
from typing import Any
import math, uuid
from research_os.core.provenance import provenance_from_mapping
from research_os.core.types import Evidence,EvidenceLevel,GateResult,GateStatus,RunManifest
from research_os.engines.calphad import CalphadRequest,UnavailableCalphadEngine
from research_os.labs.base import Lab
from research_os.metal.rules import metal_rules
from research_os.proof.engine import ProofEngine
R_J_MOL_K=8.31446261815324
class MetalLab(Lab):
    """Composition-first metallurgy: composition -> processing -> microstructure -> properties."""
    name="MetalLab"
    def __init__(self,calphad_engine=None): self.calphad_engine=calphad_engine or UnavailableCalphadEngine()
    def normalize(self,raw:dict[str,Any])->dict[str,Any]:
        b=str(raw.get("fraction_basis","atomic")).strip().lower(); percent=b in {"at%","wt%","atomic_percent","mass_percent","weight_percent"}; basis="atomic" if b in {"atomic","at","at%","atomic_percent"} else "mass" if b in {"mass","weight","wt","wt%","mass_percent","weight_percent"} else b
        rc=raw.get("components") or raw.get("composition") or {}; iterable=[{"element":k,"fraction":v} for k,v in rc.items()] if isinstance(rc,dict) else rc; items=[]
        for item in iterable:
            f=float(item.get("fraction",item.get("value"))); f=f/100.0 if percent else f; items.append({"element":str(item.get("element")).strip(),"fraction":f})
        items.sort(key=lambda x:x["element"])
        return {"name":raw.get("name"),"components":items,"fraction_basis":basis,"processing":dict(raw.get("processing") or {}),"microstructure":dict(raw.get("microstructure") or {}),"test_conditions":dict(raw.get("test_conditions") or {}),"provenance":dict(raw.get("provenance") or {}),"calphad":dict(raw.get("calphad") or {}) if raw.get("calphad") is not None else None}
    def rules(self): return metal_rules()
    def run(self,raw:dict[str,Any],experiment:str="alloy_catalog"):
        n=self.normalize(raw); m=RunManifest(lab=self.name,experiment=experiment,inputs=n); p=provenance_from_mapping(n.get("provenance"),default_source_id="metal-input"); m.provenance.append(p); ProofEngine().evaluate(m,self.rules())
        if not m.passed:return m
        fr={c["element"]:c["fraction"] for c in n["components"]}; d={"component_count":len(fr),"maximum_fraction":max(fr.values()),"minimum_nonzero_fraction":min(v for v in fr.values() if v>0)}
        if n["fraction_basis"]=="atomic": d["configurational_entropy_j_mol_k"]=-R_J_MOL_K*sum(x*math.log(x) for x in fr.values() if x>0)
        else: d["configurational_entropy_j_mol_k"]=None; d["configurational_entropy_note"]="requires atomic fractions; mass fractions were preserved without silent conversion"
        cev=Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",kind="normalized_alloy_composition",level=EvidenceLevel.E2_COMPUTATIONAL,source="MetalLab composition normalizer",provenance_ids=(p.provenance_id,),payload={"composition":fr,"fraction_basis":n["fraction_basis"],"descriptors":d,"processing":n["processing"],"microstructure":n["microstructure"],"test_conditions":n["test_conditions"]}); m.evidence.append(cev)
        c=n.get("calphad")
        if c is not None:
            if not self.calphad_engine.available:
                m.gates.append(GateResult("GATE-MET-THERMO","MET-CALPHAD-001",GateStatus.INDETERMINATE,"CALPHAD was requested but no thermodynamic engine/database is configured; no phase-stability claim may be made",diagnostics={"engine":type(self.calphad_engine).__name__})); return m
            db=c.get("database")
            if not db:
                m.gates.append(GateResult("GATE-MET-THERMO","MET-CALPHAD-002",GateStatus.INSUFFICIENT_EVIDENCE,"CALPHAD requires an explicit thermodynamic database")); return m
            try: result=self.calphad_engine.calculate(CalphadRequest(composition=fr,fraction_basis=n["fraction_basis"],temperature_k=c.get("temperature_k"),pressure_pa=float(c.get("pressure_pa",101325.0)),database=str(db),phases=tuple(c.get("phases") or ())))
            except Exception as exc:
                m.gates.append(GateResult("GATE-MET-THERMO","MET-CALPHAD-003",GateStatus.FAIL,"CALPHAD engine failed",diagnostics={"error_type":type(exc).__name__,"error":str(exc)})); return m
            ev=Evidence(evidence_id=f"EVD-{uuid.uuid4().hex[:12].upper()}",kind="calphad_equilibrium",level=EvidenceLevel.E3_PHYSICS,source=f"{result.engine} {result.engine_version or 'unknown'} / {result.database}",provenance_ids=(p.provenance_id,),payload=result.to_dict()); m.evidence.append(ev); m.gates.append(GateResult("GATE-MET-THERMO","MET-CALPHAD-003",GateStatus.PASS,"CALPHAD calculation completed",evidence_ids=(ev.evidence_id,)))
        return m
