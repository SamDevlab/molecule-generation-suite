# APODOCK-001 prospective protocol freeze v1.0

Status: **FROZEN**. This document and
[`configs/apodock001-protocol-freeze-v1.0.json`](../configs/apodock001-protocol-freeze-v1.0.json)
are normative for the first prospective APODOCK-001 run.

## Scope

The freeze covers exactly ten cases, in the committed order APD-001 through
APD-010. The benchmark source is the Seeliger & de Groot 2010 apo/holo
large-motion cohort. The source-list hash, case-metadata hash, PDB hashes,
coordinate identities, alignment eligibility, and known-site grid identities
are part of the protocol contract.

APD-010 remains in the cohort. Its structural preflight correctly reports that
the raw two-component PDB ligand is not directly Vina-ready. The immutable
BEM+MAV chemistry gate then supplies the declared covalent adapter and reports
chemistry readiness 10/10. This distinction is explicit in the manifest; it is
not a silent case exclusion.

## Scientific identity

The validator computes `protocol_hash` from the canonical JSON scientific
payload. The payload includes the benchmark, chemistry gate, receptor and
ligand preparation, boxes, Vina contract, analysis, evidence, and change
control. It excludes only the schema marker, the derived `protocol_id`, the
stored `protocol_hash`, and `operational_metadata`.

`protocol_id` is:

```text
research-os.apodock001.protocol.v1.0+fef2036e5bcd8d97
```

The full protocol hash is recorded in the JSON manifest. JSON object order and
formatting do not change the identity. A change to an input hash, chemistry
rule, preparation rule, box, Vina version or parameter, output representation,
or analysis rule changes the identity and requires a new protocol version.

## Frozen execution contract

- AutoDock Vina: 1.2.7, default Vina scoring, rigid receptor.
- Official Linux x86_64 release SHA-256:
  `f31f774f723bba7bbbe6e9d1c47577020eea9a8da16424284c043d22593570644`.
- Seed: 42; CPU: 1; exhaustiveness: 16; num-modes: 20.
- Energy range is explicitly not supplied by the current adapter. Adding it is
  a scientific change and requires a new protocol version.
- The box is derived once from transformed holo-ligand heavy atoms with 6 Å
  padding, minimum side 20 Å, maximum side 30 Å, and no result-dependent
  recalculation. The exact center, size, and grid hash for every case are in
  the JSON manifest.
- Receptors are selected apo chains converted to PDBQT with the declared
  Open Babel 3.1.1 contract, Gasteiger charges, hydrogens, and rigid mode.
- Ligands use the validated single CCD instance for APD-001..009 or the
  immutable APD-010 adapter, followed by RDKit ETKDGv3/UFF seed-42 conformer
  generation and the declared Open Babel PDBQT conversion.

## Analysis plan

The primary endpoint is same-frame, symmetry-aware heavy-atom RMSD for pose 1
against the transformed holo reference, with a 2.0 Å success threshold. The
secondary report preserves the minimum RMSD over up to 20 returned poses, all
Vina scores, pose count, and first-loss stage. Per-case vectors and explicit
denominators are retained; indeterminate cases are never silently removed.

APD-010 coordinate mapping remains an explicit indeterminate state if the
adapter cannot provide a complete mapped reference. This freeze therefore
does not predeclare a fabricated coordinate or a fabricated result.

## Verification and change control

`research_os.docking.apodock001_protocol` rejects duplicate keys, non-finite
numbers, altered case identities, changed hashes, changed boxes, changed Vina
parameters, and mismatched derived identities. The preflight script emits
`APODOCK-001 protocol: FROZEN` and never imports or invokes Vina or Open Babel.

CI runs the protocol tests and the no-docking preflight. It must not install or
execute Vina. A future execution runner must consume this manifest exclusively,
verify every hash and tool identity before starting, and fail before the first
docking process on any mismatch. No merge is automatic; any scientific change
requires a new protocol version and explicit review.
