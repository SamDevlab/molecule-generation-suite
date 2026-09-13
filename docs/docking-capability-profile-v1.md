# Docking Capability Profile v1

## Purpose

This profile makes the Research OS docking validation boundary explicit. It
describes bounded computational workflow behavior under frozen protocols; it
does not turn docking into affinity, potency, efficacy, clinical, or
experimental structural evidence. The machine-readable source is
`configs/docking-capability-profile-v1.json`, with identity
`research-os.docking.capability-profile.v1+b795a9dbd963044d`.

All entries remain `E2_COMPUTATIONAL`. The profile references historical
benchmark identities and hashes; it does not copy or rewrite their raw
evidence.

## Evidence and classification

| Context | Evidence | Capability | Primary observation |
| --- | --- | --- | --- |
| Cognate redocking | REDOCK-003 | validated in bounded domain | 8/15 pose-1 cases were <=2.0 Å under same-frame evaluation |
| Non-cognate holo cross-docking | CROSSDOCK-001 | partially validated | rank-1 3/10; any returned pose 5/10 at <=2.0 Å |
| Rigid apo docking | APODOCK-001 v1.0.2 and v1.1 | insufficiently validated | no demonstrated <=2.0 Å pose recovery in the evaluated determinate cases |
| Unknown | none | out of domain | insufficient evidence |

The REDOCK evidence uses the corrected same-frame, symmetry-aware
pose-localization semantics. The historical REDOCK v1.1 `GetBestRMS`
localization result is invalidated and is not evidence for this profile.
CROSSDOCK is a non-cognate holo, known-pocket, rigid-receptor result; it is
not cognate redocking or apo validation. APODOCK v1.1 was an exhaustiveness-32
diagnostic continuation, not evidence for a new protocol version. Current
evidence does not justify APODOCK v1.2.

## DockingLab integration

Every DockingLab run carries an explicit `docking_context` and embeds:

- `capability_profile_id` and profile hash;
- capability classification;
- E2 evidence level;
- validation source IDs;
- known limitations and interpretation boundary.

Missing or unsupported context normalizes to `UNKNOWN_DOCKING_CONTEXT` and is
classified `OUT_OF_DOMAIN`. This does not silently block an exploratory engine
calculation, but it prevents a validated capability claim. The capability
claim gate is separate from engine execution gates so a scientific result is
not relabeled as a successful capability validation merely because Vina
returned a process result.

## Same-frame and claim boundaries

The validated localization semantics do not fit, translate, or rotate a
predicted ligand onto the reference. Symmetry-aware correspondence is allowed
within the declared evaluator contract. A score is not measured affinity; a
pose is not experimental truth; one benchmark is not general validation; and
E2 remains E2 regardless of outcome.

## Failure modes

The profile separates engine failures (`EXECUTION_FAILED`,
`ADAPTER_SUBPROCESS_TIMEOUT`) from analysis failures
(`POSE_CONVERSION_FAILED`, `REFERENCE_COORDINATES_INCOMPLETE`,
`REPRESENTATION_RECONSTRUCTION_INSTABILITY`, `DERIVED_SDF_BYTE_NONDETERMINISM`)
and scientific performance failures (`POOR_RANK_1_LOCALIZATION`,
`NEAR_NATIVE_POSE_MISRANKED`, `NO_NEAR_NATIVE_POSE_RETURNED`,
`RECEPTOR_CONFORMATION_MISMATCH`). These outcomes remain visible and are not
converted into optimistic claims.

## Freeze statement

The profile identity changes when evidence, endpoint/threshold, classification,
failure-mode, or interpretation-boundary content changes. Operational paths,
timestamps, branch names, formatting, and key order do not change it.

The profile is a validation layer, not a new docking benchmark. It was frozen
after the historical campaign and before any new docking experiment.
