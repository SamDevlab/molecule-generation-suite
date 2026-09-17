# REDOCK-002 — prospective Astex holdout v1.0

**Status:** prospectively frozen before any REDOCK-002 docking outcome.

**Protocol ID:** `research-os.redocking.holdout.v1.0`

## Purpose

REDOCK-001 established that the corrected same-frame evaluator can reproduce five selected crystallographic poses under one frozen AutoDock Vina protocol. REDOCK-002 is a separate **prospective holdout** intended to test whether that result generalizes to unseen complexes without tuning against their docking outcomes.

The source pool is the Astex Diverse Set introduced by Hartshorn et al. (J. Med. Chem. 2007, 50, 726-741; DOI `10.1021/jm061277y`), a curated set of 85 diverse protein-ligand complexes developed specifically for docking validation.

No REDOCK-002 complex occurs in REDOCK-001.

## Prospectively frozen cases

| Case | PDB | Ligand | Ligand auth chain | Receptor auth chain(s) | Target class | Resolution |
| --- | --- | --- | --- | --- | --- | ---: |
| HLD-001 | `1V0P` | `PVB` | A | A | PfPK5 protein kinase | 2.00 Å |
| HLD-002 | `1W1P` | `GIO` | B | B | chitinase | 2.10 Å |
| HLD-003 | `2BM2` | `PM2` | B | B | serine protease / tryptase | 2.20 Å |
| HLD-004 | `1VCJ` | `IBA` | A | A | influenza neuraminidase | 2.40 Å |
| HLD-005 | `1TT1` | `KAI` | A | A | ionotropic glutamate-receptor ligand-binding core | 1.93 Å |

Selection was based on membership in the Astex Diverse Set, unambiguous crystallographic ligand instances, structural diversity and lack of overlap with REDOCK-001 — **not** on any REDOCK-002 Vina or RMSD result.

RCSB entry/ligand metadata used for the freeze:

- `1V0P/PVB`: https://www.rcsb.org/structure/1V0P
- `1W1P/GIO`: https://www.rcsb.org/structure/1W1P
- `2BM2/PM2`: https://www.rcsb.org/structure/2BM2
- `1VCJ/IBA`: https://www.rcsb.org/structure/1VCJ
- `1TT1/KAI`: https://www.rcsb.org/structure/1TT1

## Frozen docking protocol

To make REDOCK-002 a generalization test rather than a new tuning exercise, the docking and evaluation choices are inherited from the validated REDOCK-001 v1.2 protocol unless explicitly stated here:

- AutoDock Vina `1.2.7`;
- rigid receptor;
- Vina default scoring;
- `seed = 42`;
- `cpu = 1`;
- `exhaustiveness = 16`;
- `num_modes = 20`;
- no flexible residues;
- same RCSB PDB/source extraction policy;
- same independently generated RDKit ETKDG starting conformer with seed 42 and UFF optimization when available;
- same Open Babel preparation policy;
- same native-ligand-centered search-box rule: heavy-atom span + 12 Å, minimum side 20 Å, maximum side 30 Å;
- same-frame symmetry-aware heavy-atom RMSD;
- **no rigid-body fitting, translation, rotation or superposition after docking**;
- descriptive pose-1 success threshold `RMSD <= 2.0 Å`;
- all five cases remain in the denominator, including failures and indeterminate/out-of-domain cases.

Non-target HETATM species are not manually restored or removed case-by-case. The existing extraction policy is applied uniformly; if that makes a case unsupported, the case remains in the denominator with its first-loss classification.

## Primary endpoint

The primary endpoint is the full five-case vector of **pose-1 same-frame symmetry-aware heavy-atom RMSD** plus the count/fraction at `<= 2.0 Å` using all five prospectively frozen cases as denominator.

Secondary diagnostics:

- minimum RMSD among sampled Vina poses;
- pose count;
- Vina score by rank;
- PASS / FAIL / INDETERMINATE / OUT_OF_DOMAIN status;
- FIRST_LOSS;
- stable scientific-result identity and separate execution/environment identity.

## Interpretation rule

No case may be removed, substituted or have its receptor chain, ligand instance, box, preparation, Vina settings, evaluator or threshold changed after the first REDOCK-002 real docking execution begins because of an observed outcome.

If a methodological defect is found after execution, results remain as audit history and a new protocol version is required, following the precedent established by REDOCK-001 v1.1 -> v1.2.

## Prerequisite gate before first execution

REDOCK-002 must not be interpreted until the REDOCK-001 v1.2 scientific-identity portability correction is integrated and demonstrated to produce the same scientific hash across two otherwise equivalent executions. This gate affects provenance integrity only; it does not permit changing the REDOCK-002 case set based on future docking outcomes.

## Interpretation boundary

A successful result would support pose-reproduction generalization only across these five prospectively frozen Astex complexes under this exact protocol. It would not establish binding affinity, potency, selectivity, biological activity, toxicity, safety, efficacy, clinical performance or universal docking accuracy.
