# Project health — Research OS 3.4

Branch: `research-os-v1.3`  
Version: `3.4.0`  
Scope: Research OS only; `Biolab/` and `formolecular/` remain outside the
boundary.

## Validation status

- Full local suite: `157 passed, 1 skipped`.
- v3.4 resolution contract suite: `14 passed`.
- Python compileall and browser JavaScript syntax checks: pass.
- Fifteen bundles in the final live root: zero `FAIL`; the three metadata-only
  source-gate bundles are explicitly `INDETERMINATE`, while the battery
  resolution bundle and computational workflow bundles verify successfully.
- Resolution store: six records, zero invalid digests; history is append-only.
- Targeted static scan of `src/research_os/resolution`, `tools/resolution` and
  `web/app.js`: clean for shell execution, `eval`, external LLM clients and
  network client imports in the execution layer.
- `Biolab/` and `formolecular/`: no diff.

## Engine and data inventory

- Cantera `3.2.0`: available and executed for the bounded equilibrium trend
  protocol; evidence is `E3_PHYSICS`.
- RDKit: available for the existing molecular campaign.
- Open Babel: `NOT_CONFIGURED` in the acceptance runtime.
- AutoDock Vina: `NOT_CONFIGURED` in the acceptance runtime.
- `pymatgen`, `matminer`, `pycalphad`: not configured in the acceptance
  runtime; no CALPHAD or materials-engine result was claimed.
- NASA PCoE RW3: real ZIP retrieved, hash verified, MATLAB data parsed with
  source and locator metadata. The public record still lacks fields needed to
  close the complete degradation question.

## Promotion and stop policy

No campaign was promoted because of a model answer. AqSolDB external
validation was not faked with a same-source split. No inactive pharma control
was invented. No material property/value was invented from generic review
metadata. No computational E3 result was upgraded to E4. v3.5, v3.6 and v3.7
remain intentionally unopened until new external authority or configured
engines make their gates meaningful.
