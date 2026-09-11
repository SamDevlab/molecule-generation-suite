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

This specification, source identity, case denominator, normalization method and endpoints are frozen **before the first PB-002 PoseBusters execution**. Poor or unexpected outcomes must remain data; they cannot be used to remove cases or redefine the endpoint in v1.0.
