# BIOEXP-001 — Experimental Collaboration Package

## Scientific question

Measure the aqueous solubility of the same frozen 2×2 panel under one
pre-declared laboratory protocol.

## Purpose

The experiment is designed to quantify the factor A effect, the factor B
effect, and their interaction. No selection decision is part of this package.

## Frozen panel

| Cell | Factor A | Factor B | Compound | InChIKey | Formula |
| --- | --- | --- | --- | --- | --- |
| A0B0 | CONTROL | CONTROL | `MOLDISC-011-JE2-286E6F2BE8` | `DRIAWXDDGSORDT-KKUQBAQOSA-N` | `C30H33N3O5S` |
| A1B0 | DELTA-OH | CONTROL | `MOLDISC-014-SOURCE-DELTA-OH` | `NAZMDUVPQSKJEQ-KKUQBAQOSA-N` | `C30H33N3O4S` |
| A0B1 | CONTROL | DELTA-NSUB | `MOLDISC-014-SOURCE-DELTA-NSUB` | `DMSDTDPQGPRTNA-FDFHNCONSA-N` | `C27H35N3O5S` |
| A1B1 | DELTA-OH | DELTA-NSUB | `MOLDISC-014-SOURCE-DELTA-BOTH` | `URHJIBSBOJFXDI-FDFHNCONSA-N` | `C27H35N3O4S` |

```text
              B0                 B1
         ------------------------------
A0       A0B0               A0B1
A1       A1B0               A1B1
```

Exact isomeric SMILES and machine-readable identities are in
`experiment_request.json`, `compound_identity_table.csv`, `panel.sdf`, and
the individual MOL files.

## Requested material and characterization

Please quote 25 mg and 50 mg options per compound. Preferred purity is >=95%;
>=98% is optional. Preferred characterization is HPLC/equivalent, MS/LC-MS,
and NMR, with attributable batch and report traceability.

## Protocol status

`AWAITING_EXTERNAL_PROTOCOL_OR_QUOTE`

The following conditions are intentionally not frozen:

- `measurement_method`
- `equilibrium_or_kinetic`
- `temperature`
- `pH`
- `medium`
- `buffer`
- `ionic_strength_if_applicable`
- `compound_form`
- `target_concentration_range_if_applicable`
- `units`
- `replicate_policy`
- `sample_purity_requirement`

The laboratory should propose the method, protocol identifier, conditions,
replicate policy, sample requirements, quantification limits and raw-data or
official-report format. Human review must freeze the protocol before any real
result is submitted.

## Result boundary

**NO EXPERIMENTAL RESULT EXISTS YET.**

**THIS PACKAGE MUST NOT BE INTERPRETED AS E4 EVIDENCE.**

This is an `EXPERIMENT_REQUEST` only. `TEST_SYNTHETIC` fixtures are useful for
pipeline tests but cannot create E4. `NEXT_GENERATION_ALLOWED=NO` remains in
force, and no selection or ranking is declared.
