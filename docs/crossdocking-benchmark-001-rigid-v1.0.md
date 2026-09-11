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

## Docking protocol after the freeze

Only after all 10 directed cases pass the no-docking preflight and the exact preflight identity is frozen may a later commit enable docking.

The intended docking parameters are inherited from the validated redocking workflow:

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

## Interpretation boundary

CROSSDOCK-001 measures robustness to a non-cognate **holo receptor conformation** under a known-pocket setup. It is not blind docking, apo docking, induced-fit docking, affinity prediction, free-energy estimation, potency prediction, biological validation, or clinical evidence.

The target holo ligand is used only to define the target pocket/grid. The ligand being evaluated is always the *other* structure's ligand, and its reference pose is transferred by receptor alignment rather than ligand fitting.
