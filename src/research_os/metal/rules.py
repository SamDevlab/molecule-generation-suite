from __future__ import annotations
import math
from research_os.core.types import GateResult, GateStatus
from research_os.proof.rules import Rule
VALID_ELEMENTS=set("H He Li Be B C N O F Ne Na Mg Al Si P S Cl Ar K Ca Sc Ti V Cr Mn Fe Co Ni Cu Zn Ga Ge As Se Br Kr Rb Sr Y Zr Nb Mo Tc Ru Rh Pd Ag Cd In Sn Sb Te I Xe Cs Ba La Ce Pr Nd Pm Sm Eu Gd Tb Dy Ho Er Tm Yb Lu Hf Ta W Re Os Ir Pt Au Hg Tl Pb Bi Po At Rn Fr Ra Ac Th Pa U Np Pu Am Cm Bk Cf Es Fm Md No Lr Rf Db Sg Bh Hs Mt Ds Rg Cn Nh Fl Mc Lv Ts Og".split())
def metal_rules():
    def components(ctx,evidence):
        comps=ctx.get("components") or []
        if not comps: return GateResult("GATE-MET-COMPOSITION","MET-COMP-001",GateStatus.FAIL,"alloy composition is empty")
        bad=[c.get("element") for c in comps if c.get("element") not in VALID_ELEMENTS]
        if bad: return GateResult("GATE-MET-COMPOSITION","MET-COMP-001",GateStatus.FAIL,"unknown element symbols",diagnostics={"elements":bad})
        if len({c["element"] for c in comps})!=len(comps): return GateResult("GATE-MET-COMPOSITION","MET-COMP-001",GateStatus.FAIL,"duplicate element entries must be merged before analysis")
        return GateResult("GATE-MET-COMPOSITION","MET-COMP-001",GateStatus.PASS,"alloy components structurally valid")
    def fractions(ctx,evidence):
        vals=[float(c["fraction"]) for c in ctx.get("components") or []]
        if any((not math.isfinite(v)) or v<0 or v>1 for v in vals): return GateResult("GATE-MET-COMPOSITION","MET-COMP-002",GateStatus.FAIL,"fractions must be finite values in [0,1]",diagnostics={"fractions":vals})
        total=sum(vals)
        if not math.isclose(total,1.0,rel_tol=0,abs_tol=1e-6): return GateResult("GATE-MET-COMPOSITION","MET-COMP-002",GateStatus.FAIL,"alloy fractions must sum to one",diagnostics={"sum":total})
        return GateResult("GATE-MET-COMPOSITION","MET-COMP-002",GateStatus.PASS,"alloy fractions sum to one")
    def basis(ctx,evidence):
        value=ctx.get("fraction_basis")
        if value not in {"atomic","mass"}: return GateResult("GATE-MET-COMPOSITION","MET-COMP-003",GateStatus.FAIL,"fraction basis must be atomic or mass",diagnostics={"fraction_basis":value})
        return GateResult("GATE-MET-COMPOSITION","MET-COMP-003",GateStatus.PASS,"fraction basis declared")
    return [Rule("MET-COMP-001","Validate alloy element identities",components),Rule("MET-COMP-002","Validate normalized alloy fractions",fractions),Rule("MET-COMP-003","Require explicit atomic or mass fraction basis",basis)]
