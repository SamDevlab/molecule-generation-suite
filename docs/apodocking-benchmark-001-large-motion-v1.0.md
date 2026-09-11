# APODOCK-001 — rigid apo-receptor, known-site large-motion benchmark

Status: **prospective structural preflight only; Vina is forbidden in this phase.**

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

The cohort is the complete ten-case Table 1 benchmark from:

Daniel Seeliger and Bert L. de Groot (2010), *Conformational Transitions upon
Ligand Binding: Holo-Structure Prediction from Apo Conformations*,
PLoS Computational Biology 6(1):e1000634.
DOI: https://doi.org/10.1371/journal.pcbi.1000634

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
A. The initial no-Vina run used chain A for the sugar, failed closed with zero BEM
instances, and no docking was executed. This mapping was corrected before any
APODOCK-001 Vina job existed.

## No-Vina preflight

For each published case the preflight:

1. downloads the apo and holo PDB entries;
2. parses frozen receptor author chain A in both structures;
3. verifies the frozen holo ligand component mapping, including chain B for the
   remediated 1Y3N oligosaccharide;
4. globally sequence-aligns the receptor chains and retains identical matched Cα atoms;
5. computes one Kabsch transform from **holo receptor → apo receptor** using all
   matched identical Cα pairs;
6. applies only that rigid transform to the holo ligand reference;
7. creates the known-site grid from the transformed holo ligand using the frozen
   6 Å padding, 20 Å minimum side, and 30 Å maximum side rule;
8. validates the RCSB instance SDF for each single-CCD ligand;
9. records the branched 1Y3N ligand as requiring a dedicated covalent
   multi-component preparation adapter before Vina;
10. writes a portable structural manifest and explicitly records
    `docking_executed=false` and `vina_imported_or_invoked=false`.

No docking score, pose, RMSD outcome, or Vina binary can influence this phase.

## Prospective boundary

The first successful no-Vina artifact will be frozen in a follow-up commit,
including the structural manifest hash and per-case PDB/reference/grid identities.
Only after that freeze may an APODOCK-001 Vina job be introduced.

If a published case is structurally ineligible, the reason remains in the
preflight evidence. Cases are not replaced with easier alternatives.
