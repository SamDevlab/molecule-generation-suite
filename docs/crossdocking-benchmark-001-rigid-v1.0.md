# CROSSDOCK-001 — rigid holo-holo cross-docking v1.0

## Scientific role

CROSSDOCK-001 is a prospective receptor-conformation stress test. It asks whether the frozen Vina workflow can recover a ligand pose when the ligand is docked into a **different holo receptor conformation of the same target**, rather than the cognate receptor used for its crystal structure.

This benchmark is intentionally harder than REDOCK-001/002/003. A poor result remains scientific data; cases, directions, alignment rules, grid rules, docking parameters, or the 2 Å endpoint must not be changed after the first Vina outcome without a new protocol version.

Source benchmark context: Rueda, Bottegoni & Abagyan, *J. Chem. Inf. Model.* 2009, 49(3), 716–725, DOI `10.1021/ci8003732`, PMID `19434904`. The paper studied cross-docking and receptor flexibility across a larger benchmark. CROSSDOCK-001 uses a frozen subset of holo-holo receptor pairs as an independent stress test; it does not claim to reproduce the paper's method or results.

## Frozen selection

Published pair candidates are filtered to remove any PDB structure already observed in REDOCK-001, REDOCK-002, or the prospective REDOCK-003 cohort. Remaining pairs are ordered by:

```text
SHA-256("research-os.crossdock001.v1.0:" + pair_id)
```

The first five selected pairs are:

| Pair | Target | Structure A | Ligand A | Structure B | Ligand B |
| --- | --- | --- | --- | --- | --- |
| 1KI4–1KIM | thymidine kinase | 1KI4 chain A | BTD chain A | 1KIM chain A | THM chain A |
| 1AQ1–1DM2 | CDK2 | 1AQ1 chain A | STU chain A | 1DM2 chain A | HMD chain A |
| 1P8D–1PQ6 | LXRβ | 1P8D chain A | CO1 chain A | 1PQ6 chain B | 965 chain B |
| 1CX2–3PGH | COX-2 | 1CX2 chain A | S58 chain A | 3PGH chain A | FLP chain A |
| 1KSN–1XKA | factor Xa | 1KSN chain A | FXV chain A | 1XKA chain C | 4PP chain C |

Both directions are mandatory, giving **10 directed cases**. The denominator is all 10 after the structural preflight is frozen.

## Structural preflight — before Vina

No docking outcome is permitted during the preflight phase.

For each directed case:

1. Download both RCSB PDB entries.
2. Require the declared protein chain to contain parseable amino-acid Cα coordinates.
3. Require exactly one declared ligand instance on the declared ligand author chain.
4. Define the target-receptor pocket as target-chain residues with any heavy atom within **10 Å** of the target structure's cognate ligand.
5. Globally align source and target receptor-chain sequences with deterministic Needleman–Wunsch scoring (`match=2`, `mismatch=-1`, `gap=-2`; ties `diagonal > up > left`).
6. Retain only identical aligned residues that belong to the target pocket.
7. Require at least **8** matched pocket Cα pairs.
8. Compute one Kabsch rigid transform mapping the source receptor pocket into the target-receptor coordinate frame. Alignment RMSD is recorded but is **not** used to exclude difficult conformational changes.
9. Fetch the source and target RCSB ligand-instance SDF references and require their heavy-atom counts to match the corresponding PDB ligand instances.
10. Apply the receptor-derived rigid transform to the source ligand reference. The ligand itself is never independently fitted to the target ligand.
11. Construct the prospective docking box from the union of the target holo-ligand heavy atoms and the transformed source-reference heavy atoms, with the existing `+6 Å` per-side padding rule, minimum side `20 Å`, maximum side `30 Å`. A required side above `30 Å` is structurally out of domain.

The preflight records source/target PDB hashes, alignment transform, alignment RMSD, reference coordinate identities, grid identity, and a selection-manifest hash. It explicitly reports `docking_executed=false` and `vina_imported_or_invoked=false`.

### Portable prospective freeze

The first successful no-docking run (`34605661949`) established the same 10 structural cases, but its manifest hashed raw SVD/Kabsch floating-point values. A later no-Vina reproduction showed machine-epsilon differences (~1e-14) across runners despite unchanged PDB hashes, ligand coordinate identities, matched residues and physical grids. That first manifest (`9631023f89b2971a503cab193989e0ac8d3eb53642d27fdcbf5572e5e04e4a26`) is retained only as audit provenance and is **not** the v1.0 structural identity.

Before any CROSSDOCK-001 Vina execution, v1.0 was corrected to canonicalize floating structural values to 9 decimal places for identity hashing. The portable freeze is:

```text
freeze/capture head SHA          = 4192379f4a88262a20e2e64a46b486cd2047aa18
workflow run                     = 34607126629
artifact id                      = 10266663459
artifact ZIP SHA-256             = 1c2a1f62e4290b3c21cfc918579c6f34e362c82c63a943bc2d8d4e1ee9cdcb5d
eligible directed cases          = 10 / 10
portable selection manifest hash = 852f027bdc55ba8c2def9d3fde0a80e70cf6a4ffc375b4eb8a696e436b681215
docking executed                 = false
Vina binary present              = false
```

All ten directions exceeded the minimum eight matched pocket Cα pairs. Observed receptor-pocket alignment RMSDs ranged from approximately **0.239 Å to 1.070 Å** and all prospective grids remained inside the frozen 20–30 Å domain. Alignment RMSD was descriptive only and did not remove any case.

The portable preflight identities are sealed in `crossdock001_freeze.py`; a later docking runner must reproduce them before Vina is allowed to execute.

## Docking protocol after the freeze

Only after all 10 directed cases pass the no-docking preflight and the exact portable preflight identity is independently reproduced may a later commit enable docking.

The docking parameters are inherited from the validated redocking workflow:

- AutoDock Vina `1.2.7`;
- rigid target receptor;
- independent ligand starting conformer from RDKit ETKDGv3, seed `42`, followed by UFF when parameters are available;
- Open Babel receptor/ligand PDBQT preparation;
- Vina seed `42`;
- CPU `1`;
- exhaustiveness `16`;
- `20` requested modes;
- no post-docking minimization, pose repair, ligand fitting, or reranking.

## Primary endpoint

The source ligand's crystallographic pose is transformed into the target-receptor coordinate frame **using only the frozen receptor-pocket transform**. Predicted Vina poses are then evaluated by the same symmetry-aware heavy-atom Cartesian RMSD logic used by REDOCK v1.2, with no ligand superposition or fitting.

Primary success criterion:

```text
Vina rank-1 same-frame symmetry-aware heavy-atom RMSD <= 2.0 Å
```

Secondary descriptive endpoints may include best-of-N RMSD and first near-native rank, but they cannot replace the frozen rank-1 primary endpoint.

## Evaluator audit: direct-SDF v1.0 invalidated, representation v1.1

The first real Vina execution occurred only after the portable structural freeze was sealed. Vina completed all ten directed docking cases, but the original evaluator trusted Open Babel's PDBQT→SDF chemical reconstruction directly. In `XDK-05-1` that reconstruction produced neutral tetravalent nitrogen atoms that RDKit could not sanitize. The docking itself completed and produced 20 poses; the failure occurred only when converting the serialized pose representation into an evaluable RDKit molecule.

That first evaluator attempt is retained, but **invalidated as a complete scientific result** because only 9/10 frozen pose-1 endpoints were evaluable:

```text
workflow run                     = 34612986306
artifact id                      = 10269612880
artifact ZIP SHA-256             = 4be2256cfeac8aa05d60cb1327587ba682faa90a27a405ada6b2cf0f9dd5cbd5
invalidated scientific hash      = f7e9e77a6b375d14b05686de681478205b4e84bbcceafbfa8131de7814b09411
Vina cases executed              = 10 / 10
evaluable pose-1 cases           = 9 / 10
technical indeterminate case     = XDK-05-1
```

The correction is `research-os.crossdocking.pose-representation.v1.1`. It applies **uniformly to every returned pose in all ten cases**, not only to the failed case:

1. Parse the PDBQT→SDF pose without sanitizing the reconstructed chemistry.
2. Take ligand chemistry/connectivity from that case's known pre-docking `starting_conformer.sdf`.
3. Require an exact element/connectivity heavy-atom graph correspondence between the starting ligand and docked pose.
4. Copy the docked heavy-atom coordinates exactly into the known ligand chemistry template.
5. Reassign stereochemistry from the docked 3D coordinates and require the restored molecule to sanitize.
6. Evaluate the restored representation with the unchanged REDOCK v1.2 same-frame RMSD metric.

The correction does **not** use crystallographic ligand coordinates for mapping, translate or rotate a docked pose, fit the ligand, minimize it, rerank poses, alter Vina scores, alter grids, replace cases, or change the 2 Å endpoint. Each pose records the atom mapping and requires `max_heavy_atom_coordinate_delta_angstrom = 0.0`.

The original Vina/docking protocol remains `research-os.crossdocking.rigid.v1.0`; only the pose-representation/evaluation layer is revised to v1.1.

## Validated v1.1 result

The first complete v1.1 execution is workflow run `34615447564` on head `ddb7906b661d87b6f417cee8ff855de170a5e646`. All ten directed cases were technically evaluable and every returned pose passed the representation audit with **0.0 Å heavy-atom coordinate movement**, no crystallographic mapping coordinates, no rigid fit, and no minimization.

```text
artifact id                  = 10271091364
artifact ZIP SHA-256         = a5094acefffa7d52e30d887ef765d7524e728faff0beb9cf5eb6048caa663e91
evaluable pose-1 cases       = 10 / 10
rank-1 RMSD <= 2 Å           = 3 / 10 (30%)
any returned pose <= 2 Å     = 5 / 10 (50%)
pose-1 RMSD mean             = 3.9466324496 Å
pose-1 RMSD median           = 3.7489267768 Å
scientific_result_hash       = d1d5b980816837301c1fe70d2c0a397ba4a0e662bced7aa17bb118c61f2bff16
```

| Case | Direction | Rank-1 RMSD (Å) | Best returned RMSD (Å) | First ≤2 Å rank | Primary |
| --- | --- | ---: | ---: | ---: | --- |
| XDK-01-1 | 1KI4 → 1KIM | 1.9728 | 1.0529 | 1 | PASS |
| XDK-01-2 | 1KIM → 1KI4 | 0.7721 | 0.7721 | 1 | PASS |
| XDK-02-1 | 1AQ1 → 1DM2 | 5.2686 | 4.7620 | — | FAIL |
| XDK-02-2 | 1DM2 → 1AQ1 | 5.1950 | 2.8063 | — | FAIL |
| XDK-03-1 | 1P8D → 1PQ6 | 3.6346 | 2.0740 | — | FAIL |
| XDK-03-2 | 1PQ6 → 1P8D | 3.8633 | 3.2376 | — | FAIL |
| XDK-04-1 | 1CX2 → 3PGH | 0.9291 | 0.9291 | 1 | PASS |
| XDK-04-2 | 3PGH → 1CX2 | 6.6721 | 1.3018 | 4 | FAIL |
| XDK-05-1 | 1KSN → 1XKA | 2.4767 | 2.4767 | — | FAIL |
| XDK-05-2 | 1XKA → 1KSN | 8.6819 | 1.6314 | 6 | FAIL |

The primary endpoint therefore falls from the REDOCK-003 prospective **8/15 = 53.3%** rank-1 localization rate to **3/10 = 30%** under non-cognate holo receptor conformations. Two additional directions (`XDK-04-2` and `XDK-05-2`) contained a near-native pose but ranked it below pose 1, while the remaining five primary failures had no returned pose within 2 Å. This is evidence of reduced robustness under receptor-conformation change, with both ranking and pose-set limitations represented; it is not an affinity or biological-performance claim.

A documentation-only follow-up commit is used to request an independent reproduction of this same frozen experiment. The result is not considered closed until the same scientific hash is reproduced on that later head.

## Interpretation boundary

CROSSDOCK-001 measures robustness to a non-cognate **holo receptor conformation** under a known-pocket setup. It is not blind docking, apo docking, induced-fit docking, affinity prediction, free-energy estimation, potency prediction, biological validation, or clinical evidence.

The target holo ligand is used only to define the target pocket/grid. The ligand being evaluated is always the *other* structure's ligand, and its reference pose is transferred by receptor alignment rather than ligand fitting.
