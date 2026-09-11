# APODOCK-001 — rigid apo-receptor, known-site large-motion benchmark

Status: **prospective structural preflight frozen; Vina is still forbidden in this PR.**

## Scientific question

APODOCK-001 asks whether the unchanged rigid-receptor docking stack can localize a
known holo ligand when the receptor is supplied in a genuinely unbound apo
conformation that undergoes a large ligand-induced structural transition.

This is **not blind docking**. The holo ligand is used only to define the known
binding-site location, the evaluation reference, and the same frozen
6 Å-per-side padding / 20–30 Å grid limits used by the redocking program.
The apo receptor remains rigid. This isolates sensitivity to receptor
conformational mismatch from site-search failure.

## Prospective source cohort

The cohort is the complete ten-case Table 1 benchmark from Daniel Seeliger and
Bert L. de Groot (2010), *Conformational Transitions upon Ligand Binding:
Holo-Structure Prediction from Apo Conformations*, PLoS Computational Biology
6(1):e1000634. DOI: https://doi.org/10.1371/journal.pcbi.1000634

The publication reports apo→holo backbone rearrangements from 2.1 to 7.1 Å.
The ten pairs are frozen in table order before any APODOCK-001 Vina execution:

| ID | Target | Apo | Holo | Holo ligand mapping | Published BB RMSD (Å) | Binding-site RMSD (Å) |
|---|---|---|---|---|---:|---:|
| APD-001 | GLUR2 | 1FTO | 1FTM | AMQ, auth A | 2.2 | 2.0 |
| APD-002 | GLUCO | 1JEJ | 1JG6 | UDP, auth A | 2.1 | 2.6 |
| APD-003 | ALLO | 1GUD | 1RPJ | ALL, auth A | 4.4 | 4.0 |
| APD-004 | RIB | 1URP | 2DRI | RIP, auth A | 4.3 | 3.5 |
| APD-005 | LEUB | 1USG | 1USI | PHE, auth A | 7.1 | 6.8 |
| APD-006 | EPSP | 1RF5 | 1RF4 | SPQ, auth A | 3.7 | 4.6 |
| APD-007 | OSMO | 1SW5 | 1SW2 | BET, auth A | 5.0 | 4.4 |
| APD-008 | GUA | 1EX6 | 1EX7 | 5GP, auth A | 3.6 | 3.9 |
| APD-009 | HEXO | 2E2N | 2E2O | BGC, auth A | 3.0 | 1.9 |
| APD-010 | ALGI | 1Y3Q | 1Y3N | BEM + MAV oligosaccharide, chain B | 4.8 | 3.6 |

Source-list SHA-256:
`3eaa3c45732efa05c1e5f4f468275e8f23e7b82ea9632f5c91dac1a30d62ebfc`

Frozen case-metadata SHA-256 after current-PDB carbohydrate mapping correction:
`5bd7d26535417c10d124bf6aac1f5355b6c9e8c90bdb01d670b18d0ccff3ab6b`

RCSB confirms the single-component mappings used above. 1Y3N is different:
the published alginate disaccharide is an oligosaccharide entity composed of BEM
and MAV. PDB carbohydrate remediation (entry major version 2.0, 2020-07-29)
represents that oligosaccharide as its own chain B while the protein remains chain
A. Initial no-Vina run `34642494049` used chain A for the sugar and failed closed
with zero BEM instances. No docking was executed. The mapping was corrected in
`fa0a737eaa1989856474068f330c3c2c52d74344` before any APODOCK-001 Vina job existed.

## No-Vina preflight

For each published case the preflight downloads apo/holo PDB entries, parses the
frozen receptor chains, verifies the ligand mapping, globally sequence-aligns the
receptors, retains identical matched Cα atoms, computes one Kabsch transform from
**holo receptor → apo receptor**, applies only that rigid transform to the holo
ligand, derives the known-site grid, and validates the RCSB instance SDF for every
single-CCD ligand. APD-010 remains a two-component covalent glycan and is marked as
requiring a dedicated preparation adapter before Vina.

No docking score, pose, RMSD outcome, or Vina binary can influence this phase.

## Frozen successful preflight

First successful no-Vina preflight after the carbohydrate mapping correction:

- workflow run: `34642755042`
- head SHA: `fa0a737eaa1989856474068f330c3c2c52d74344`
- artifact: `apodock001-preflight-v1.0`, ID `10280154166`
- artifact ZIP SHA-256: `2026a042818c4ec021fea672d4ceba72a31734c61da4ce8c97413dcb3bfcace8`
- structurally eligible: **10/10**
- directly chemistry-ready for Vina: **9/10**
- selection manifest hash: `c5fae682ecf6b7e8884de8b4d02fd052d306ea3b5d421b6ad44814289afae805`
- `docking_executed=false`
- `vina_imported_or_invoked=false`

`src/research_os/docking/apodock001_freeze.py` now freezes the portable per-case
PDB hashes, reference-coordinate hashes, transformed-reference hashes, matched-Cα
counts, grid hashes, structural status, and chemistry-readiness state. Subsequent
no-Vina runs must reproduce those identities exactly. The artifact ZIP digest is
execution/package metadata; the portable manifest hash is the scientific
structural identity gate.

## Boundary after this PR

This PR does not add or execute Vina. A later change may prepare APODOCK-001
execution only after this frozen preflight reproduces successfully. APD-010 must
receive an explicit covalent multi-component ligand preparation path or remain a
predeclared unsupported chemistry case; it must not be silently simplified or
replaced.
