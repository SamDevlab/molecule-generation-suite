# Research OS 3.4 — evidence-gap resolution

Branch: `research-os-v1.3`  
Version: `3.4.0`  
Scope: `Research OS` only. `Biolab/` and `formolecular/` were not modified.

## What was added

- `GapResolution` is an append-only, hash-checked record with the requested
  gap, strategy, sources, datasets, engines, runs, evidence before/after,
  status and remaining gap. `ResolutionStore` rejects a reused resolution ID.
- `ConditionMatcher` returns `MATCH`, `PARTIAL_MATCH`, `INCOMPATIBLE` or
  `UNKNOWN`; only `MATCH` is comparable. No incompatible material or battery
  observation is compared as if it were matched.
- `MaterialObservation` and `ElectrochemicalObservation` preserve source
  locators, methods, units, uncertainty and explicit unknowns.
- Receptor and ligand preparation retain their existing Open Babel protocols,
  input/output hashes and manifests. Docking resolution adds a
  `DockingReproducibilityAssessment` with three seeds when the executables are
  available and caps docking at `E2_COMPUTATIONAL`.
- The NASA PCoE RW3 adapter reads MATLAB data members with `scipy.io.loadmat`.
  ZIP scripts are not executed, and no missing capacity, resistance or
  uncertainty value is imputed.
- Live resolution and the second stop challenge are exposed at
  `/api/campaigns/resolution-challenge` and
  `/api/campaigns/unresolvable-challenge`; the Codex provider can select or
  narrate only, while Labs and the Ledger remain the source of truth.

## Live acceptance

Artifact: `.research-os-live-3.4-final3/real-resolution-acceptance.json`  
Provider: local Codex CLI, `gpt-5.6-luna`, `CODEX_LIVE`, no external LLM API.  
Discovery: 11 catalog candidates, 3 primary campaigns and 2 secondary
campaigns. Six append-only resolution attempts were recorded, including the
live selected-gap attempt. Status counts were 1 `BLOCKED`, 3
`PARTIALLY_RESOLVED` and 2 `UNRESOLVED`. The provider created no scientific
evidence. The unresolvable challenge was returned with
`NOT_ATTEMPTED_BY_DESIGN`.

The exact first challenge was:

> Encontre entre as pesquisas existentes um gap científico real que pareça resolvível com as ferramentas e fontes atualmente disponíveis. Tente resolvê-lo de ponta a ponta. Se descobrir que não é resolvível, demonstre exatamente por quê e escolha no máximo mais um gap. Não altere os critérios para produzir um resultado positivo.

The live provider selected `GAP-COMB-VALIDATION`. The actual resolution ran
Cantera `3.2.0`, `gri30.yaml`, H2, air, 300 K, 101325 Pa at φ `0.8`, `1.0`
and `1.2`. Outputs were 2167.5218 K, 2380.4487 K and 2364.7217 K. The
tested sequence was not monotonic, so the result is not a monotonic trend
claim. It remains `PARTIALLY_RESOLVED` because the original gap requires a
matched experiment at `E4_CURATED_EXPERIMENTAL`; E3 simulation was not
promoted.

The NASA PCoE artifact was retrieved from the official NASA Open Data resource
on 2026-09-03 local time, with 140,923,718 bytes and SHA-256
`4e757b8b4e574202c32702000e1002f7a235d1c83a5729cef584ce528f3a4859`.
Parsing found four cells (`RW1`, `RW2`, `RW7`, `RW8`) and 67,631 recorded
steps. The step schema supplies measured voltage, current, temperature and
time; `capacity_ah`, `resistance_ohm` and per-observation uncertainty remain
unknown. One nonphysical temperature sentinel pattern in RW2 was excluded
using the declared `[-100, 100] degC` plausibility filter, not replaced.

## Stop decision

v3.4 is complete as an evidence-closure milestone, but the scientific gaps
that require external data remain open:

- AqSolDB external validation: the available dataset is the same source lineage
  as training and is not eligible as an independent test; promotion remains
  `NOT_PROMOTED`.
- Materials: the registered review/standard/database metadata did not provide
  a record-level, condition-complete hydrogen-embrittlement observation.
- Pharma: `obabel` and `vina` were not found on `PATH`, and no Python bindings
  were configured. The 1PXX receptor/ligand preparation and three-seed docking
  were therefore not run.
- Battery: the public artifact is real and parsed, but the missing fields keep
  the condition-complete degradation question partially resolved.

Because the remaining blockers are real external-data/tool blockers, v3.5–v3.7
were not started. Advancing would require inventing evidence or changing the
criteria. NIST WebBook remains a database/reference-data source, never a
physics engine.
