# Legacy to Research OS

The migration is a set of auditable boundaries, not a rewrite of historical
files.

```text
legacy candidate/source
  -> CandidateGenerator (synthetic=true)
  -> MoleculeLab (deterministic structure properties)
  -> LigandPreparation / ReceptorPreparation
  -> DockingLab / DockingCampaign (E2 ceiling)
  -> PharmaLab
  -> Evidence -> ResearchBundle -> sealed RunManifest -> Ledger
```

The aerospace path is deliberately different:

```text
FuelLab -> Cantera-backed CombustionLab -> PropulsionLab
```

If Cantera, its mechanism, or the protocol is missing, the physics branch is
`INDETERMINATE` and downstream steps are skipped. No heuristic result is
substituted.

## Status vocabulary

`ACTIVE` means preserved and still present; `MIGRATING` means a replacement
boundary exists but parity/evidence gates are incomplete; `REPLACED` requires
validated parity for the declared scope; `DEPRECATED` and `RETIRED` require
explicit dependency and gate checks. No legacy component is deleted in v1.8.

