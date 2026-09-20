# MOLDISC-012 — STEP2-DEMETHYL-01 non-cognate docking in 1KZK

Status: **executed and closed; first CI result preserved with deterministic scientific identity**

## Scientific question

MOLDISC-011 selected one candidate upstream using its frozen AqSolDB
structural-coverage rule. MOLDISC-012 asks only whether that exact candidate
can complete the existing 1KZK/JE2 pocket cross-docking protocol reproducibly.

The candidate is `STEP2-DEMETHYL-01`,
`MOLDISC-011-JE2-286E6F2BE8`, with InChIKey
`DRIAWXDDGSORDT-KKUQBAQOSA-N`.

## Frozen provenance and boundaries

- MOLDISC-011 parent program hash:
  `8cb29619a82ca4680424c1b37c9bdce37b83e6cc8d570788435e1e9a62b159ff`;
- operational MOLDISC-010 reference hash:
  `360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b`;
- MOLDISC-010 score used for candidate selection: **no**;
- MOLDISC-010 score used for protocol selection: **no**;
- MOLDISC-010 score used as success threshold: **no**;
- no favorable-score threshold exists in MOLDISC-012;
- primary endpoint: reproducible technical completion.

The candidate, target, grid derivation and engine settings are frozen before
the first observed MOLDISC-012 score. The historical MOLDISC-010 score is not
an input to any MOLDISC-012 decision.

## Frozen target and protocol

- REDOCK-003 case: `ATX-007`;
- PDB: `1KZK`;
- native ligand: `JE2`, author chain `A`;
- receptor author chains: `A+B`;
- docking context: `NON_COGNATE_HOLO_CROSSDOCKING`;
- capability: `PARTIALLY_VALIDATED`;
- evidence: `E2_COMPUTATIONAL`;
- grid: derived from the exact crystallographic JE2 reference with the
  existing `research-os.redocking.v1.1` native-ligand box rule;
- RDKit ETKDGv3 seed `42`, UFF when parameters are available;
- Open Babel receptor: `-h --partialcharge gasteiger -xr`;
- Open Babel ligand: `-h --partialcharge gasteiger`;
- AutoDock Vina `1.2.7`, seed `42`, CPU `1`, exhaustiveness `16`,
  `num_modes=20`, scoring function `vina`.

The grid is recalculated and its hash is recorded at execution time. The
historical grid hash is not substituted for a newly derived grid.

## First preserved result

The first green CI execution is preserved in
`validation/moldisc-012-first-run-v1.json`:

- GitHub Actions run: `35477594856` (`moldisc-012-ci`), result `PASS`;
- independent runs A/B: identical program scientific hash;
  `e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776`;
- technical status: `PASS` for both runs;
- returned scored poses: `16`;
- ordered pose scores (kcal/mol): `[-11.6, -10.194, -9.739, -9.411,
  -9.251, -9.111, -9.044, -9.01, -8.914, -8.849, -8.813, -8.781,
  -8.759, -8.718, -8.674, -8.656]`;
- pose 1: `-11.6 kcal/mol`;
- derived grid hash:
  `a0bf032d8bdb1bc20f13f298d604673cac1d2c7da8596cc228ec6602b5989aef`;
- native JE2 structure hash:
  `82b48b534ff870fb8a922ed62da905bf77fe2e54f2420143986a4c5f9b9c9a4b`;
- receptor scientific identity:
  `ec55df9f302eb6b63669085023520cb66eb224c66ab15368a95997dc2fcd7c55`;
- ligand scientific identity:
  `609b8d75caf0018e1d704a24976f622c51fbfcff61d7554a55fe12be1f864f30`;
- Vina scientific output hash:
  `09a014a56ab3eb31c6e419d618a3b381e6357c2ccd18c387ce8acba5d08ddf07`.

The raw native-reference SDF and receptor PDBQT hashes differed between A/B
only because of transport metadata and temporary paths. Their normalized
scientific identities were identical and the raw values are preserved in the
validation artifact.

## Identity and reproduction

Each run writes `program_manifest.json`, `scientific_payload.json`,
`transport_provenance.json`, `program_report.md`, and the technical docking
files. Scientific identity excludes raw transport metadata such as temporary
paths, PDBQT `REMARK` path differences, and ModelServer transport metadata.
Independent CI runs must agree on candidate identity, target identity, native
reference structure, receptor and ligand scientific identities, derived grid,
ordered pose scores/count, Vina scientific output and program scientific hash.

RMSD to native JE2 is exactly
`NOT_APPLICABLE_DIFFERENT_LIGAND_GRAPH`; no native-JE2 RMSD is calculated.

## Interpretation

Technical completion is bounded computational evidence. It does not establish
measured affinity, free energy, a correct binding pose, protease inhibition,
potency, efficacy, safety or clinical utility.
