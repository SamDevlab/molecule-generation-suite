# PB-002 — Astex-20 PoseBusters validation v1.0

## Role

PB-002 is a retrospective physical/chemical plausibility validation over the **sealed rank-1 poses from REDOCK-003 run 280**. It does not rerun docking, does not rerank poses and is not a new independent holdout.

Its purpose is orthogonal to REDOCK-003 localization: REDOCK-003 asks whether Vina placed the ligand near the crystallographic binding pose; PB-002 asks whether those already-produced rank-1 poses satisfy the frozen PoseBusters `redock` checks after repairing only representation information lost in the PDBQT-to-SDF round trip.

## Frozen source

- source benchmark: `REDOCK-003`
- source protocol: `research-os.redocking.astex20.v1.0`
- evaluator protocol: `research-os.redocking.v1.2`
- source run: `34546751594` (run 280)
- source artifact ID: `10179660428`
- source artifact ZIP SHA-256: `fb0dadb67186eb2899b4c79f0a0a67683a16783cf834c587d43cdac076a98b7f`
- source scientific result hash: `e4e4693f890b86327fac16b547966fe64862045d1562c4340dcc3d7d4a06b762`
- source summary hash: `7fff66446032e26e4fa77d4c348a5cc5de499495025fcbf979f0e5124a316fd8`
- sealed cases: `ATX-001` through `ATX-015` in their REDOCK-003 frozen order
- sealed source localization result: `8/15` rank-1 same-frame RMSD <= 2 Å

The PB-002 runner fails closed if benchmark/protocol/scientific hash, case identity/order, source denominator or the sealed `8/15` localization count differs.

## Frozen PoseBusters configuration

- protocol ID: `research-os.posebusters.astex20.v1.0`
- benchmark ID: `PB-002`
- PoseBusters version: `0.6.5`
- configuration: `redock`
- upstream configuration blob SHA-1: `8bcceebd7901e06759176d3a2b6b35965033464a`
- `max_workers = 0`
- `full_report = False`

## Representation normalization

The same v1.1 normalization already validated for the earlier ten poses is reused unchanged:

1. chemical identity/bond orders come from the independently generated `starting_conformer.sdf`;
2. every heavy-atom coordinate comes exactly from the sealed Vina `pose_01.sdf`;
3. no crystallographic coordinates are used for atom mapping;
4. no translation, rotation, fitting, minimization or reranking is performed;
5. stereochemistry is cleared and reassigned from the docked 3D coordinates;
6. the normalization fails if heavy-atom connectivity differs or if any docked heavy atom moves.

This normalization addresses representation information lost by PDBQT serialization; it does not improve a pose geometrically.

## Endpoints

All endpoints use all 15 frozen rank-1 poses in the denominator.

- **source localization:** sealed REDOCK-003 same-frame symmetry-aware heavy-atom RMSD <= 2 Å;
- **PB-valid:** all official PoseBusters `redock` binary outputs pass, including PoseBusters' RMSD binary;
- **PB-plausible:** all official PoseBusters `redock` binary outputs except its RMSD binary pass;
- **combined:** source localization passes and PB-plausible passes.

PB-plausible is kept separate from localization so a chemically/geometrically plausible pose is not automatically called correctly localized, and a localized pose is not automatically called physically plausible.

## Scientific identity

The portable PB-002 scientific hash includes the frozen protocol, PoseBusters identity, source scientific identity, endpoint definitions, per-case source RMSD, representation-normalization metadata, all PoseBusters binary outcomes and aggregate summary.

Runtime paths and environment metadata are excluded from the scientific hash. The exact run/artifact ZIP provenance is audit evidence and is intentionally outside the portable scientific payload.

## Claim boundary

PB-002 is retrospective over an already-observed REDOCK-003 cohort. It can characterize physical/chemical plausibility of those 15 rank-1 poses and the overlap between plausibility and localization. It is **not** independent generalization evidence and does not establish binding affinity, potency, biological activity, efficacy, safety or clinical relevance.

## Prospective execution boundary

The protocol, source identity, 15-case denominator, normalization method and endpoints were frozen at commit `c93b31575ff85bd8e9dcbda01a190a8a7f863558` before any PB-002 outcome existed. Dedicated freeze-only workflow run `34597231474` passed without downloading REDOCK-003 or executing PoseBusters.

The first outcome-producing change was the later commit `c67470fa299965ac2ae00eadd14391eeb31110a3`. Poor or unexpected outcomes remained data and were not used to remove cases or redefine v1.0.

## Frozen outcome

The first PB-002 execution was dedicated workflow run `34597366020` on head `c67470fa299965ac2ae00eadd14391eeb31110a3`.

```text
source localization            =  8 / 15 = 53.33%
PB-plausible                    = 15 / 15 = 100.00%
PB-valid                        =  8 / 15 = 53.33%
localized AND PB-plausible      =  8 / 15 = 53.33%
scientific_result_hash          = aa3df8b21d610917f70867eb19fbdf78ed976a60b7061fbd9029c76abcc31e1a
artifact_id                     = 10263150297
artifact_zip_sha256             = 7099667ebeb810e49364d252e53f546e914a4aed054833f3ffd375e332343a11
artifact_size_bytes             = 18303
```

The downloaded artifact ZIP independently matched GitHub's SHA-256 digest. Its JSON contains exactly 15 records. For all 15 records:

- `max_heavy_atom_coordinate_delta_angstrom = 0.0`;
- starting-conformer/reference connectivity matches;
- starting-conformer/reference formula matches;
- restored formula equals template formula;
- every non-RMSD PoseBusters binary is `true`.

The seven PB-valid failures are exactly the seven source localization failures (`ATX-003`, `ATX-004`, `ATX-006`, `ATX-009`, `ATX-012`, `ATX-013`, `ATX-014`), and in every one the only failed PoseBusters binary is `rmsd_≤_2å`.

## Independent reproduction

A documentation-only successor commit `2f831f13babbb9dbeb8164afd8d01ae8c4194dea` triggered dedicated workflow run `34597627696`. It reproduced the scientific result exactly:

```text
source localization            =  8 / 15
PB-plausible                    = 15 / 15
PB-valid                        =  8 / 15
localized AND PB-plausible      =  8 / 15
scientific_result_hash          = aa3df8b21d610917f70867eb19fbdf78ed976a60b7061fbd9029c76abcc31e1a
artifact_id                     = 10263180825
artifact_zip_sha256             = 799186fac9b8fd2ce7fc1abf67cd291cc7e9233c8678f53ff92388e7ef50ecbe
artifact_size_bytes             = 18303
```

A second documentation-only head (`efacd877aecf0d5c84ac415e2a9b8fd8e05e4124`) reproduced the same scientific hash again in workflow run `34597929687`; its artifact ID was `10262816530` and ZIP SHA-256 was `2807181f2641e96a7eb2aada37973b00bb01b216562ced7e61889374bc485351`.

The raw artifact ZIP digest changed between executions while the portable scientific hash remained identical, demonstrating the intended scientific identity behavior.

## Post-outcome source-integrity hardening

After the outcome and its independent reproductions were already fixed, final code review found that PB-002 verified the **declared** REDOCK-003 scientific hash but did not independently recompute that hash from the downloaded report content. This was an input-integrity gap, not a scientific-method issue.

The runner was therefore hardened to recompute REDOCK-003's portable scientific hash with the same `redocking_v12_identity.scientific_result_hash` function that originally generated it, and to fail closed unless the recomputed value equals the sealed `e4e4693f...b762` identity. A regression test explicitly rejects a source whose declared hash is correct but whose recomputed scientific content hash is not.

This hardening does not change the 15 cases, source artifact, coordinates, PoseBusters version/configuration, representation normalization, endpoints, denominator or interpretation. The authentic sealed source is required to reproduce the same PB-002 scientific result after this implementation hardening.

## Interpretation

PB-002 supports a narrow interpretation: within this sealed 15-pose set, PoseBusters did not identify an additional physical/chemical plausibility failure beyond localization. It does **not** show that the seven misplaced poses are biologically correct, nor does it identify the cause of their localization errors.
