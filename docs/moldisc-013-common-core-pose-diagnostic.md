# MOLDISC-013 — common-core pose geometry diagnostic

Status: **CLOSED_FIRST_RESULT_PRESERVED**

## Scientific question

MOLDISC-013 compares the already selected and already docked DEMETHYL-03 /
STEP2-DEMETHYL-01 pair over their exact shared heavy-atom core. It does not
generate molecules, select molecules, search for a better score, or test
affinity.

The comparison is made in the unchanged `ATX-007 / 1KZK / JE2` receptor frame.
The parent and child dockings are replayed and must reproduce their frozen
scientific hashes before any pose geometry is analyzed.

## Frozen parents and chemistry

- MOLDISC-010 hash:
  `360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b`;
- MOLDISC-012 hash:
  `e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776`;
- DEMETHYL-03 parent: 40 heavy atoms;
- STEP2-DEMETHYL-01 child: 39 heavy atoms;
- shared core: exactly 39 heavy atoms;
- the child must be an exact element-labeled, connectivity-valid heavy
  subgraph of the parent.

Atom indices are not trusted. Graph mappings and automorphisms are enumerated
explicitly, and the minimum valid chemical mapping is used for each pose pair.

## Frozen metric

The primary metric is `RECEPTOR_FRAME_COMMON_CORE_RMSD`. For every parent pose
and child pose, the implementation removes hydrogens, normalizes connectivity
defensively, validates each pose against its source molecule, enumerates valid
common-core mappings, and computes the direct coordinate displacement:

`sqrt(mean(||xyz_parent - xyz_child||^2))`

No Kabsch alignment, rigid-body fitting, centering, translation normalization,
or rotation normalization is performed. Coordinates already share the
receptor frame, and moving them would erase the quantity being measured.

The complete pairwise matrix is expected to be `20 x 16`. The summaries are
descriptive only: rank-1 pair, global minimum pair, and each rank-1 pose versus
the opposite ensemble. There is no RMSD threshold and no scientific PASS rule
based on a number.

## Scores and evidence boundary

Historical docking scores are preserved only as parent-run provenance. They
are not used for candidate selection, common-core definition, pair selection,
or success thresholding. Rank 1 is a docking-engine rank, not an experimentally
validated pose.

MOLDISC-013 inherits at most `E2_COMPUTATIONAL` evidence from the
`NON_COGNATE_HOLO_CROSSDOCKING` / `PARTIALLY_VALIDATED` parent context. It is a
derived descriptive geometry analysis and does not establish affinity, binding
conservation experimentally, potency, efficacy, safety, or superiority.

## First CI execution

The first complete execution passed in GitHub Actions run `35480342435` from
the protocol-freeze commit `7947adf1a7653926c9756d414d44bd182a295ec4`.
MOLDISC-010 replayed with hash
`360ef9eb66981287781a971a7e09aebbe2749be765af5b4c6dcb33e3839eb48b` and
MOLDISC-012 replayed with hash
`e8c66a7726a3b191723e0dea072afdb5e4d4d9202b142eff83fe6d19c623f776`.

The resulting matrix contained 320 cells (`20 x 16`). The rank-1 pair was
`1.828019792 Å`; the global minimum was `1.675514326 Å` at parent rank 3 and
child rank 5. The parent rank-1 to child-ensemble minimum and the child
rank-1 to parent-ensemble minimum were both `1.828019792 Å`, at the opposite
rank-1 pose. Analysis A/B produced identical hashes, including mapping hash
`3e59b38463d647c88816927ad23d038b574b4b7d3138ae33714978d9e471bd32` and
matrix hash `d580968a05a03053269421bebaae1eb03aa80ab9b62cd3fadee2538fb5591386`.

The preserved validation record is
[`validation/moldisc-013-first-run-v1.json`](../validation/moldisc-013-first-run-v1.json).
