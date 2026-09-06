# REAL USE 001 — Breakage Log

Campaign: `REAL-USE-001-COX2-CROSS-STRUCTURE`  
Status: `BLOCKED_BY_PRODUCT_GAP`  
Release: Research OS `5.0.0`  
Base: `3176a48742489ccbb72caafe4af00df5b5ae2286`  
Branch: `research-use-001-cox2-cross-structure`

This log records the first real-use boundary. No workaround was used, the
Research OS core was not modified, and no parallel ResearchBundle path was
created.

## BRK-001

- stage: Phase 1 — canonical campaign entry
- trigger: a new external COX-2 campaign was requested for PDB entries 5KIR and 5IKR
- expected behavior: create a new ResearchQuestion/ResearchProgram/campaign using registered APIs and attach new official sources
- actual behavior: the released `CampaignManager` exposes a static problem/source catalog containing `P-PHARMA-01` and `SRC-RCSB-1PXX`, but no generic external-campaign registration path; 5KIR and 5IKR are not registered
- scientific impact: a new campaign cannot be represented in the canonical campaign history or advanced to a canonical ResearchBundle
- security impact: none; the static catalog prevented unreviewed source or tool injection
- workaround available: construct a parallel campaign runner or manually create a bundle
- workaround used: NO
- classification: `PRODUCT_GAP`
- severity: HIGH
- proposed future fix: add a reviewed external-source/campaign ingestion contract with append-only lineage and bundle integration

## BRK-002

- stage: Phase 5 — structure inspection
- trigger: the campaign requires chain-level mmCIF inspection, unresolved atoms/residues, alternate locations, waters, metals/cofactors and preparation decisions
- expected behavior: use a registered scientific structure parser and persist its inspection manifest
- actual behavior: official RCSB entry/entity/assembly records were retrievable, but no registered mmCIF/validation-report parser is available in the release runtime; detailed structure fields were not inferred from raw text
- scientific impact: receptor selection and preparation cannot be reproduced safely enough for comparative docking
- security impact: none; external files remained DATA ONLY and were not executed
- workaround available: install or call an unregistered parser, or write an ad hoc parser
- workaround used: NO
- classification: `PRODUCT_GAP`
- severity: HIGH
- proposed future fix: register a pinned mmCIF/validation parser and persist its version, inspection output and transformation lineage

## BRK-003

- stage: Phase 7 — cognate redocking gate
- trigger: pose recovery requires a predeclared RMSD definition, atom mapping and threshold
- expected behavior: use a registered RMSD/pose-recovery capability before candidate docking
- actual behavior: no registered RMSD, pose-recovery or cognate-redocking capability exists in the release
- scientific impact: the required redocking gate cannot be evaluated; comparative candidate docking would be unjustified
- security impact: none
- workaround available: implement an ad hoc RMSD function or select a post hoc criterion
- workaround used: NO
- classification: `PRODUCT_GAP`
- severity: HIGH
- proposed future fix: register a tested pose-recovery Lab with predeclared mapping, symmetry and threshold semantics

## BRK-004

- stage: Phase 8 — bounded engine execution
- trigger: the canonical planner proposed `DockingLab`, but the required preparation and docking executables were probed before execution
- expected behavior: run registered Open Babel and AutoDock Vina with recorded versions, hashes and commands
- actual behavior: `OpenBabelEngine.available = false` and `VinaEngine.available = false`; canonical planning returned `INDETERMINATE` with `ORACLE-ENGINE-001` and missing input configuration `ORACLE-CONFIG-001`
- scientific impact: no receptor preparation, ligand preparation, redocking, candidate run or cross-structure claim was produced
- security impact: none; no external executable was downloaded or invoked
- workaround available: install/configure executables or invoke an unregistered tool
- workaround used: NO
- classification: `RESOURCE_UNAVAILABLE` / `PRODUCT_GAP`
- severity: HIGH
- proposed future fix: make engine readiness and artifact-input contracts explicit before campaign admission, without weakening the stop gate

## BRK-005

- stage: Phase 4/5 — optional validation-report retrieval
- trigger: the official RCSB validation-report URL was attempted for each structure
- expected behavior: retrieve and hash the official validation report when available
- actual behavior: the RCSB validation-report endpoint returned HTTP 403 for both 5KIR and 5IKR; entry metadata and mmCIF files were retrieved successfully
- scientific impact: validation-report-derived quality fields remain unavailable; no claim depending on them was made
- security impact: none; the response was not treated as executable content
- workaround available: use an unregistered mirror or bypass the official endpoint restriction
- workaround used: NO
- classification: `EXTERNAL_SOURCE_ACCESS_LIMITATION`
- severity: MEDIUM
- proposed future fix: support an approved, provenance-preserving validation-report source or record the official access failure as a first-class source state
