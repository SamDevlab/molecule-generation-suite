# APD-010 BEM/MAV chemistry gate v1.0

Status: **chemical preflight complete; docking remains outside this change.**

The immutable APODOCK-001 structural preflight still records APD-010 as 24
experimental heavy-atom coordinates and `chemistry_ready_for_vina: false`.
This is a separate derived chemistry gate; it does not rewrite the structural
manifest.

## Declared chemistry

The adapter consumes the exact RCSB CCD ideal SDF plus matching CCD CIF for:

- **BEM** — beta-D-mannopyranuronic acid, `C6H10O7`, 13 heavy atoms;
  CCD atom `O1` is the declared leaving atom and `C1` is the donor endpoint.
- **MAV** — alpha-D-mannopyranuronic acid, `C6H10O7`, 13 heavy atoms;
  `O4` is the acceptor endpoint.

The PDB 1Y3N `LINK` record is the experimental evidence for the BEM C1–MAV
O4 connection. The PDB is not used to infer missing chemistry or to generate
a conformer.

## Deterministic transformation

`research-os.apd010.bem-mav@1.0.0` performs exactly these operations:

1. Verify the SDF/CIF source hashes and reconcile atom names, elements, charges,
   and bond orders against the CCD.
2. Normalize only the validated explicit CCD hydrogens into RDKit implicit
   valence; no protonation heuristic is applied.
3. Remove the CCD-declared BEM O1 leaving atom.
4. Add one single covalent bond between BEM C1 and MAV O4.
5. Run controlled sanitization and fail closed on invalid valence, unsupported
   elements, dummies, aromaticity, fragmentation, or an unexpected inventory.
6. Discard conformers and operational metadata before calculating chemical
   identity.

The output is one fragment, 25 heavy atoms, formal charge 0, and formula
`C12H18O13`. Chemical identity is a hash of formula, charge, heavy-atom count,
and canonical isomeric SMILES; coordinates, atom labels, timestamps, paths, and
serialization are excluded.

## Gate result and CLI

Run:

```powershell
$env:PYTHONPATH = "src"
py -3.11 scripts/preflight_apd010_bem_mav.py
```

The JSON report separates structural input identity, chemical input identity,
chemical output identity, transformation provenance, and diagnostics. The
derived APODOCK chemistry gate is **10/10**: nine cases inherit the immutable
direct-CCD readiness records and APD-010 is admitted only through this adapter.
The report records the known missing experimental coordinate `BEM O4`; it does
not fabricate it. `starting_conformer_generated` remains false.

No Vina was executed.
