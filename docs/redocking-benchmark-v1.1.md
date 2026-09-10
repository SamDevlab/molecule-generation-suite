# REDOCK-001 — frozen redocking benchmark v1.1

**Status:** frozen before the first real docking execution.

**Protocol ID:** `research-os.redocking.v1.1`

## Why v1.1 exists before any result

The original v1 protocol (`docs/redocking-benchmark-v1.md`, commit `c462a990fa8097b9f3b3e0998d96be71a6edfe72`) used one `selected author chain` field for both the native-ligand instance and receptor extraction. During implementation review, before any Vina outcome was produced, this was found to be structurally wrong for `1HVR`: HIV-1 protease is a dimer and the ligand-bound site requires receptor chains A and B.

No v1 docking result exists. v1 is retained unchanged as a pre-execution audit artifact and is **superseded before execution**. v1.1 fixes only the chain-role ambiguity and is the first protocol eligible for execution.

## Scientific question

For a predeclared set of experimentally resolved protein–ligand complexes, what heavy-atom pose RMSD is obtained after removing the native ligand, preparing receptor/ligand inputs, redocking the ligand with a fixed AutoDock Vina protocol, and comparing predicted poses with the crystallographic reference?

## Frozen benchmark set

| Case | PDB | Native ligand | Ligand author chain | Receptor author chains | Target | X-ray resolution |
| --- | --- | --- | --- | --- | --- | ---: |
| RDK-001 | `1STP` | `BTN` | `A` | `A` | streptavidin | 2.60 Å |
| RDK-002 | `3PTB` | `BEN` | `A` | `A` | beta-trypsin | 1.70 Å |
| RDK-003 | `1HVR` | `XK2` | `A` | `A,B` | HIV-1 protease | 1.80 Å |
| RDK-004 | `1M17` | `AQ4` | `A` | `A` | EGFR kinase domain | 2.60 Å |
| RDK-005 | `1IEP` | `STI` | `A` | `A` | c-Abl kinase domain | 2.10 Å |

The cases were selected before docking outcomes. No case may be removed because its result is poor.

Public entry provenance:

- `https://www.rcsb.org/structure/1STP`
- `https://www.rcsb.org/structure/3PTB`
- `https://www.rcsb.org/structure/1HVR`
- `https://www.rcsb.org/structure/1M17`
- `https://www.rcsb.org/structure/1IEP`

Raw coordinate acquisition uses `https://files.rcsb.org/download/<PDB>.pdb` for these legacy four-character entries. Every acquired file is SHA-256 hashed; URL identity alone is insufficient provenance.

## Engine identity

- docking engine: **AutoDock Vina 1.2.7**;
- Vina executable contract: `RESEARCH_OS_VINA_EXECUTABLE` or `vina` on `PATH`;
- preparation/conversion engine: Open Babel through the canonical `OpenBabelEngine` contract (`RESEARCH_OS_OPENBABEL_EXECUTABLE` or `obabel` on `PATH`);
- executable versions and prepared-artifact hashes are mandatory provenance;
- Python Vina bindings are not treated as proof that the external Vina executable exists.

## Frozen docking parameters

- scoring: Vina default;
- rigid receptor;
- `seed = 42`;
- `cpu = 1`;
- `exhaustiveness = 16`;
- `num_modes = 20`;
- default Vina `energy_range` unless the canonical engine contract later records an explicit value without changing search/ranking behavior;
- no flexible residues;
- no per-complex post-result parameter tuning.

## Search-box rule

The box is deliberately native-ligand-centered because this is **redocking**, not blind docking.

For each axis:

1. center = midpoint between minimum and maximum native-ligand heavy-atom coordinate;
2. required size = native-ligand heavy-atom span + `12.0 Å`;
3. minimum side = `20.0 Å`;
4. maximum side = `30.0 Å`;
5. if an unclamped required side exceeds `30.0 Å`, the case is `OUT_OF_DOMAIN` for v1.1.

Center, sizes, unclamped sizes, and deterministic grid hash are recorded.

## Receptor extraction

- retain `ATOM` records belonging to the frozen receptor author chains;
- remove the benchmark ligand;
- remove crystallographic waters;
- remove non-polymer ions, solvent, and other small molecules in v1.1;
- do not silently add a cofactor or a different polymer chain;
- an empty or unparsable receptor is fail-closed.

This intentionally simple receptor policy may disadvantage cases that need a non-polymer cofactor. Such a failure is evidence about protocol scope and remains in the benchmark record; changing the policy requires another protocol version.

## Reference ligand and independent starting ligand

- reference pose = the frozen native-ligand HETATM instance for `ligand_author_chain`;
- a single native-ligand residue instance must be identifiable; ambiguity fails closed;
- native coordinates are used only for the evaluation reference and search-box derivation;
- starting docking coordinates must be generated independently from the reference pose;
- starting conformer generation uses the parsed ligand graph with RDKit ETKDG and `randomSeed = 42`, followed by UFF optimization when available;
- if the ligand graph cannot be parsed or the independent conformer cannot be generated, the case is non-passing.

The generated starting conformer is content-hashed before PDBQT preparation.

## PDBQT preparation

For v1.1, the implementation may use the already registered Open Babel adapter with fixed, recorded options:

- receptor: add hydrogens, assign Gasteiger partial charges, output rigid PDBQT (`-xr` write behavior);
- ligand: add hydrogens, assign Gasteiger partial charges, retain ligand torsion-tree behavior;
- Vina output poses are converted one pose at a time to SDF for graph-aware RMSD evaluation.

If Open Babel cannot preserve/produce a chemically compatible ligand graph between reference and predicted pose, RMSD evaluation fails closed. There is no coordinate-only atom-index fallback.

## Primary endpoint

**Pose-1 symmetry-aware heavy-atom RMSD (Å)** against the crystallographic reference, after graph identity validation and optimal alignment/mapping.

Secondary diagnostics:

- minimum RMSD among the up to 20 declared poses;
- Vina scores by pose/rank;
- pose count.

Secondary metrics cannot replace pose-1 RMSD after outcomes are known.

## Aggregate endpoints

- mean pose-1 RMSD over cases with valid RMSD;
- median pose-1 RMSD over cases with valid RMSD;
- full five-case pose-1 RMSD vector with `null` retained for non-passing cases;
- count/fraction with pose-1 RMSD `<= 2.0 Å`, with **all five frozen cases as denominator**;
- counts of PASS / FAIL / INDETERMINATE / OUT_OF_DOMAIN;
- per-case `FIRST_LOSS`.

The 2 Å threshold is descriptive. It does not establish affinity or efficacy.

## Fail-closed case gates

A passing case requires all of the following:

1. RCSB coordinate download succeeded and raw SHA-256 was recorded;
2. frozen receptor chain(s) contain protein atoms;
3. exactly one intended native-ligand residue instance is selected;
4. reference ligand is chemically parseable;
5. independent starting conformer was generated;
6. search box is in-domain under the frozen rule;
7. receptor and ligand PDBQT preparation executed with attributable Open Babel version;
8. Vina identifies as version 1.2.7 and executes with the frozen parameters;
9. at least one pose is produced;
10. pose/reference heavy-atom graph identity permits symmetry-aware mapping;
11. pose-1 RMSD is finite.

Failed cases stay in the five-case denominator.

## Mandatory provenance

Each case records:

- case/PDB/ligand/chain identities;
- RCSB source URL and raw hash;
- reference ligand, receptor extraction, starting conformer, prepared receptor, prepared ligand, and Vina-output hashes;
- Vina and Open Babel versions plus executable paths/identities where available;
- exact preparation/docking options;
- grid center/size/hash;
- per-pose score/RMSD;
- status and first loss;
- runtime/platform information.

The aggregate report has a deterministic scientific-result hash over protocol identity, frozen case identities, case statuses, source/content hashes, grid definitions, and observed pose metrics. Runtime metadata is recorded separately.

## Interpretation boundary

REDOCK-001 v1.1 can support only pose-reproduction statements for this fixed protocol and benchmark set. It cannot establish measured binding affinity, potency, biological activity, selectivity, toxicity, safety, clinical efficacy, or universal docking accuracy.

## Change control after first execution

Once the first real v1.1 Vina execution starts, none of the following may change in response to outcomes:

- case list;
- native ligand identities;
- ligand/receptor chain sets;
- source extraction policy;
- starting-conformer seed;
- search-box rule;
- preparation options;
- Vina version/seed/CPU/exhaustiveness/mode count;
- primary endpoint;
- 2 Å descriptive threshold;
- five-case denominator policy.

Any change requires a new protocol version while preserving v1.1.
