# REAL USE 001 — Human COX-2 Cross-Structure Docking Robustness

## Campaign

- campaign: `REAL-USE-001-COX2-CROSS-STRUCTURE`
- title: Human COX-2 Cross-Structure Docking Robustness
- status: `BLOCKED_BY_PRODUCT_GAP`
- release: Research OS `5.0.0`
- base release HEAD: `3176a48742489ccbb72caafe4af00df5b5ae2286`
- working branch: `research-use-001-cox2-cross-structure`
- package verified: `5.0.0`
- Research OS core modified: NO
- `Biolab/` modified: NO
- `formolecular/` modified: NO

### Primary question

Does the existing COX-2 docking conclusion or candidate ranking remain
directionally stable when transferred from the registered murine 1PXX receptor
context to independent human COX-2 crystal structures under a predeclared
common docking protocol?

### Required secondary question

Can cognate-ligand redocking reproduce each human experimental binding pose
sufficiently well to justify comparative docking on that receptor?

### Hypothesis

The hypothesis was intentionally not promoted to a result. The campaign was
designed to determine whether the earlier 1PXX ordering survives a human,
cross-structure computational test, subject first to a cognate-redocking gate.

## Prior registered state

The historical state was read-only:

- receptor: `1PXX`, `Mus musculus`, COX-2/PTGS2, chain A in the declared docking protocol;
- prior candidates: diclofenac and celecoxib;
- prior claim: `CLM-COX2-1PXX-V2`, a supported E2 statement that diclofenac reference docking completed three reproducible computational replicates under the declared murine 1PXX protocol;
- prior decision: `DECISION-REAL-01-1DC0442BB0EA`, protocol-limited separation under identical 1PXX docking conditions;
- prior gap: `GAP-DOCKING-E2-ONLY`, including receptor-structure dependence and the absence of independent structural comparison;
- known limitation: the historical preparation excluded HEM because the Open Babel conversion was incompatible; docking remained E2 computational evidence, not measured affinity or efficacy.

The historical record explicitly classified identical 1PXX reruns as low
information gain. No identical 1PXX run was repeated here.

## Canonical Research OS discovery result

The existing canonical path was exercised as planning-only. The release
catalog contains `P-PHARMA-01` and `SRC-RCSB-1PXX`, but neither 5KIR nor 5IKR.
The default planner generated a `DockingLab` plan with status `INDETERMINATE`
and these first blocking diagnostics:

- `ORACLE-ENGINE-001`: AutoDock Vina unavailable;
- `ORACLE-CONFIG-001`: receptor, ligand and grid inputs missing from the canonical plan.

The registered engine probe was:

| Capability | Release result |
|---|---|
| `VinaEngine` | unavailable |
| `OpenBabelEngine` | unavailable |
| mmCIF/validation parser | no registered capability |
| RMSD/pose-recovery capability | no registered capability |
| dynamic external campaign/source ingress | not available in the static campaign catalog |

This is a product/runtime boundary, not a scientific result about COX-2.

## External primary sources

All downloaded content was treated as DATA ONLY. No file, archive or embedded
content was executed. Source manifests were created through the canonical
`SourceRegistry` API under:

`.research-use-001-cox2-cross-structure/source-registry/manifests/`

Raw official records are preserved under:

`.research-use-001-cox2-cross-structure/sources/`

| PDB | Official record | Revision observed | Organism | Mutation count | Method | Resolution | Cognate ligand | Entry SHA256 | mmCIF SHA256 |
|---|---|---:|---|---:|---|---:|---|---|---|
| 5KIR | The Structure of Vioxx Bound to Human COX-2 | 2.3, 2026-08-12 | *Homo sapiens* | 0 | X-ray diffraction | 2.697 Å | RCX, Rofecoxib | `77f886173d2c06f76f9299799cc0c50ecd8ada8ef6068e58c97ac2072c261513` | `927fb3eb69423db63849eb15842dc475172964f1bbdb63ac97eacf4867c54243` |
| 5IKR | The Structure of Mefenamic Acid Bound to Human COX-2 | 2.2, 2026-08-12 | *Homo sapiens* | 0 | X-ray diffraction | 2.342 Å | ID8, mefenamic-acid record name `2-[(2,3-DIMETHYLPHENYL)AMINO]BENZOIC ACID` | `0fd101e7f08bc808fb839acf0124a9115633058ec4f978bfcfbc3ee5ce921a99` | `a4a20672b28f87d32a4cdff8ae7dbdbe4c94af40bc86d4b7caf0122d860cf472` |

Official retrieval URLs:

- 5KIR entry: `https://data.rcsb.org/rest/v1/core/entry/5KIR`
- 5KIR mmCIF: `https://files.rcsb.org/download/5KIR.cif`
- 5IKR entry: `https://data.rcsb.org/rest/v1/core/entry/5IKR`
- 5IKR mmCIF: `https://files.rcsb.org/download/5IKR.cif`

Retrieval timestamps and complete metadata are in the four source manifests.
The official validation-report endpoint returned HTTP 403 for both entries and
was not replaced by an unregistered mirror.

## Deterministic source inspection

Official entry/entity/assembly records establish:

- both structures contain one protein entity with auth chains A and B;
- the reported assembly is assembly 1 with two polymer instances;
- both entries identify human PTGS2/COX-2 and a mutation count of zero;
- 5KIR lists RCX plus COH, NAG, NH4, GOL and PO4 non-polymer entities;
- 5IKR lists ID8 plus COH, NAG, BOG and NH4 non-polymer entities;
- COH is recorded as `PROTOPORPHYRIN IX CONTAINING CO`; it was not silently relabeled as HEM;
- no receptor chain, cofactor, water, alternate-location, unresolved-atom, protonation or glycosylation preparation decision was made.

The last point is deliberate. The release has no registered mmCIF/validation
parser capable of producing the required complete preparation audit, so the
campaign stops instead of inferring those fields from incomplete inspection.

## Redocking gate

No cognate redocking was executed.

- criterion: not declared post hoc;
- RMSD definition: not declared because no registered pose-recovery capability exists;
- seeds: none;
- Vina version/configuration: unavailable;
- receptor/ligand preparation: not executed;
- gate: `MISSING_REGISTERED_CAPABILITY` and `RESOURCE_UNAVAILABLE`;
- interpretation: no conclusion about the human receptors or their ligands is permitted.

The campaign therefore did not proceed to candidate docking. No ranking,
Spearman/Kendall value, seed variability, receptor variability or preparation
sensitivity was calculated.

## Evidence, claims and decisions

| Item | Result |
|---|---|
| New Research OS Evidence | 0 |
| Codex-created Evidence | 0 |
| EvidenceLevel mutations | 0 |
| New ResearchBundle | 0 — canonical bundle path blocked |
| New claim | none |
| Claim revision | none |
| Decision revision | none |
| Gap closed | none |
| Gap refined | no; the existing cross-structure gap remains open |

The only supported new statement is source/provenance metadata: official RCSB
records for 5KIR and 5IKR were retrieved and hashed. That metadata is not
docking evidence and does not validate a pose or ranking.

## Required scientific answers

- A. Cognate redocking: **not executed**; no valid/failed pose-recovery conclusion.
- B. Ranking change between structures: **INSUFFICIENT_EVIDENCE**; no candidate runs were justified.
- C. Murine-to-human change: **INSUFFICIENT_EVIDENCE**; the transfer was not tested.
- D. Seed robustness: **not assessed** for the new receptors.
- E. Receptor-conformation robustness: **not assessed**.
- F. Prior claim status: **unchanged**; the historical 1PXX E2 claim remains scoped to its original protocol. It is not extended to human structures.
- G. Prior decision: **unchanged**, because no valid new decision evidence exists.
- H. Gap closed: none.
- I. Gap remaining: cross-structure structural preparation, cognate redocking and independent E2 comparison remain open.

## Product behavior and stop decision

The product successfully:

- preserved the frozen 5.0.0 release;
- accepted the research question and enforced the E2 computational ceiling;
- retrieved official source records as data;
- produced source hashes through `SourceRegistry`;
- surfaced engine/configuration unavailability instead of fabricating execution;
- preserved the prior claim and decision without overwriting history.

The product failed to provide the capabilities required for this new external
campaign. The detailed records are in
`REAL_USE_001_BREAKAGE_LOG.md`. The first blocking layer was Phase 1 campaign
ingress (`BRK-001`), followed by structure inspection (`BRK-002`), RMSD
redocking (`BRK-003`) and engine availability (`BRK-004`).

The campaign is therefore correctly closed as `BLOCKED_BY_PRODUCT_GAP`. No
core correction, version bump, Live call, unregistered executable or
workaround was used.

## Reproduction

1. Checkout `3176a48742489ccbb72caafe4af00df5b5ae2286`.
2. Use package `research-os-core==5.0.0`.
3. Inspect the source manifests under `.research-use-001-cox2-cross-structure/source-registry/manifests/`.
4. Verify each manifest `document_hash` against its corresponding official artifact in `sources/`.
5. Probe the registered engines; the campaign must stop if Vina/Open Babel are unavailable.
6. Do not create a manual ResearchBundle. A future maintenance cycle must first add the missing registered capabilities and canonical external-campaign ingress.
