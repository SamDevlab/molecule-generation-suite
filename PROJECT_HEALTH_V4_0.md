# Project health — Research OS 4.0

Status: PASS validation release.

- Branch: `research-os-v1.3`
- Required predecessor artifacts: v3.9, v3.10, v3.11 and v3.12 PASS
- v4 matrix: 100 fixed + 30 new Codex Live = 130 cases
- Reproduction: 20 cases; stress: 50 PASS
- Final exam: A supported bounded calculation, B OOD `NO_DECISION`, C
  external blocker stopped before execution
- Follow-ups: 20/20 grounded
- Scientific invariant violations: 0
- Security failures: 0
- False supported decisions: 0
- False no-decisions: 0

The expected Python 3.11 Cantera skip remains documented in the earlier
milestones because Cantera is installed on the local host. Python 3.12 has no
skip. Legacy `Biolab/` and `formolecular/` files are preserved and remain in
MIGRATING review status.

The canonical machine-readable health evidence is
`.research-os-live-4.0/master-validation.json`.
