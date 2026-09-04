# Research OS v4.1 — Real Research Deployment

Status: **PASS**
Branch: `research-os-v1.3`
Checkpoint: v4.0 `6962266`
Release: `4.1.0`

v4.1 adds an auditable outcome-impact contract and executes deeper research
against the scientific state already registered by Research OS. The release
does not promote Evidence, change EvidenceLevels, overwrite claims, or treat
Codex reasoning as scientific evidence.

## Gate result

All v4.1 acceptance checks passed:

- 6 bounded ResearchPrograms;
- 42 substantive questions and 15 questions generated from the current state;
- 10 `ResearchOutcomeImpact` records;
- 3 `KNOWLEDGE_CHANGED`, 2 `DECISION_CHANGED`, 2 `GAP_REFINED`, 1
  `UNCERTAINTY_REDUCED`, 1 `NO_MATERIAL_CHANGE`, and 1 `BLOCKED_EXTERNAL`;
- 2 declared high-confidence solubility failure cases;
- 6 protocol-sensitivity assessments;
- a real Cantera condition-boundary decision was revisited;
- the prior solubility claim was narrowed by an append-only `ClaimRevision`;
- 2 low-information docking steps were skipped;
- all new runs were sealed, bundled, and registered in a fresh Ledger;
- PlanValidator, bundle verification, Ledger verification, and the full local
  regression gate passed.

The complete machine-readable record is
`.research-os-live-4.1/research-outcome-impact.json`.

## Scientific boundary

The COX-2 result remains E2 computational evidence for murine RCSB 1PXX. The
current runtime did not expose AutoDock Vina, so no new exhaustiveness result
was guessed or reported. Cantera results remain E3 physics simulations and
were not promoted to experiment. The solubility model remains an E1
sample-specific model with an independent external-validation gap. Battery
and materials conclusions retain missing fields and external blockers.

v4.2 is not declared complete by this release. User-provided corpus status
remains `AWAITING_USER_CORPUS` until real private material is supplied and
reviewed.
