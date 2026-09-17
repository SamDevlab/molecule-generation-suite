# REPRO-001 — Vina same-seed reproducibility diagnostic

## Role

REPRO-001 is a **retrospective technical diagnostic**, not a new prospective docking benchmark. It was created after CROSSDOCK-001 revealed that repeated AutoDock Vina 1.2.7 executions could produce different exact pose outputs despite the same frozen inputs and nominal stochastic controls.

The purpose is to separate three different questions:

1. Are the docking inputs identical across technical replicates?
2. Is the primary scientific endpoint stable across replicates?
3. Are exact poses, RMSDs, secondary endpoints, and scientific-result hashes bitwise stable?

A negative answer to question 3 must not be hidden by changing seeds, reranking, replacing cases, or redefining the endpoint after observing the results.

## CROSSDOCK-001 evidence

The diagnostic was motivated by three complete CROSSDOCK-001 v1.1 technical replicates using the same frozen protocol:

- AutoDock Vina 1.2.7;
- Vina seed 42;
- CPU 1;
- exhaustiveness 16;
- up to 20 modes;
- identical frozen receptor/ligand preparation and grid rules;
- pose representation `research-os.crossdocking.pose-representation.v1.1`;
- primary endpoint: rank-1 same-frame symmetry-aware heavy-atom RMSD <= 2 Å.

Observed complete technical replicates:

| Replicate | Rank-1 <=2 Å | Any returned pose <=2 Å | Scientific result hash |
| --- | ---: | ---: | --- |
| first complete run | 3/10 | 5/10 | `d1d5b980816837301c1fe70d2c0a397ba4a0e662bced7aa17bb118c61f2bff16` |
| independent rerun | 3/10 | 6/10 | `efcfbf91b1c243c824c60686787cb18427423f8ff0400ac5e0dde37836efb4ea` |
| third technical replicate | 3/10 | 5/10 | `d1d5b980816837301c1fe70d2c0a397ba4a0e662bced7aa17bb118c61f2bff16` |

The first and third replicates were exactly identical at the scientific-result level. The middle replicate differed in exact poses/RMSDs and crossed the secondary 2 Å threshold for `XDK-03-1`, changing the best-of-returned-pose count from 5/10 to 6/10.

The primary classification remained **3/10 in all three replicates, with the same three primary successes**.

## Input audit

Comparing the complete evidence bundles showed that the receptor and ligand PDBQT inputs were byte-identical across the compared runs, the frozen grids were unchanged, and the same Vina 1.2.7 binary digest was used.

Therefore the observed difference is classified as **execution-level non-bitwise reproducibility** rather than input/protocol drift.

This finding is intentionally narrower than claiming that Vina is generally nondeterministic. It documents what was observed for this exact workflow on GitHub-hosted Ubuntu runners.

## Reusable analyzer

`research_os.docking.reproducibility.analyze_replicates()` compares two or more docking reports with the same case set and records:

- per-replicate primary and secondary success counts;
- per-case primary classification stability;
- per-case secondary classification stability;
- pose-1 RMSD ranges;
- minimum returned-pose RMSD ranges;
- pose-count variation;
- rank-1 Vina score variation;
- receptor/ligand/grid input-identity stability;
- the number of distinct scientific-result hashes;
- a deterministic diagnostic hash over the comparison result.

CLI usage:

```bash
python scripts/analyze_docking_reproducibility.py \
  replicate-1.json replicate-2.json replicate-3.json \
  --output reproducibility.json
```

## Interpretation

For CROSSDOCK-001, the defensible conclusion is:

- exact pose output is not proven bitwise reproducible across hosted-runner executions;
- the best-of-returned-pose secondary endpoint was threshold-sensitive in one case;
- the frozen **rank-1 primary endpoint was stable at 3/10 across three complete technical replicates**.

Future docking benchmarks should report categorical endpoint stability separately from exact-output reproducibility when repeated execution evidence is available.
