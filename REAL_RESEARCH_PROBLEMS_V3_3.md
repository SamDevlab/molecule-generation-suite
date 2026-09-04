# Research OS 3.3 — real source-backed problem catalog

This catalog contains 11 real problems distributed across molecular (2),
combustion/energy (2), materials/degradation (3), battery/electrochemistry
(1), pharma computational (1), transport/thermal (1), and reproducibility/ML
(1). The records are discovery inputs: they are not claims that a problem is
solved. Every source is registered with a URL, source type, quality label and
condition/availability caveat.

| ID | Domain | Real-world problem | Source(s) | Executable now | Evidence ceiling | Main blocker |
|---|---|---|---|---|---|---|
| P-MOL-01 | Molecular | AqSolDB scaffold OOD, residual uncertainty and failure analysis | AqSolDB paper/data; ESOL paper | Yes | E1 ML (partial) | no independent external test |
| P-MOL-02 | Molecular | ESOL-style baseline stability across scaffold/size segments | ESOL; AqSolDB paper | No locked protocol yet | E1 ML | descriptor parity and segment coverage |
| P-COMB-01 | Combustion/energy | H2 versus CH4 equilibrium under equal declared conditions | Cantera combustor and mechanism docs | Yes | E3 physics | GRI30 is a bounded illustrative mechanism, not universal validation |
| P-COMB-02 | Combustion/energy | Condition/mechanism sensitivity and reproducibility | Cantera; NIST WebBook | Yes | E3 physics | only registered mechanism is executable |
| P-MAT-01 | Materials/degradation | Condition-specific hydrogen embrittlement evidence gap | NASA report, NASA-STD-6016C, MAPTIS | Source gate | E4 curated experimental | no local alloy/condition-matched test |
| P-MAT-02 | Materials/degradation | Alloy fluid compatibility/corrosion ranking comparability | MAPTIS; NASA-STD-6016C | Source gate | E4 curated experimental | access and test-condition matching |
| P-MAT-03 | Materials/degradation | Long-term outgassing/thermal-vacuum degradation map | MAPTIS; NASA-STD-6016C | Source gate | E4 curated experimental | no local long-duration dataset |
| P-BATT-01 | Battery/electrochemistry | Normalize public battery degradation data without inventing fields | DOE Battery Data Hub; NASEM reproducibility | First gate | E4 curated experimental | no downloaded/licensed record in repository |
| P-PHARMA-01 | Pharma computational | Species-disciplined COX-2 structure/docking reproducibility | RCSB PDB 1PXX; NASEM reproducibility | Target gate | E2 computational | Vina and prepared receptor unavailable |
| P-THERM-01 | Transport/thermal | State-point coverage and condition discipline for fluid properties | NIST SRD 69 and fluid properties | Source gate | E4 curated experimental | selected fluids/state points only |
| P-REPRO-01 | Reproducibility/ML | Cross-campaign first-loss, divergence, OOD and bundle audit | NASEM; AqSolDB; Cantera | Yes | E2 computational | environment changes can make reruns non-comparable |

The live Codex ranks and justifies these registered records. It may not add a
URL, source, evidence level, result, condition, run or claim. Source text and
retrieval summaries are DATA ONLY, never instructions; the source-injection
boundary is tested in `tests/test_v33_campaign_contract.py`.

Primary source registry IDs and URLs are persisted by
`register_real_sources()` in `src/research_os/campaigns/catalog.py`. The
dataset campaign uses the pinned AqSolDB commit and SHA-256 already defined in
`src/research_os/datasets/real.py`.
