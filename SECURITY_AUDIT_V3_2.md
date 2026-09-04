# Security Audit — Research OS 3.2 Live Oracle

## Live boundary

The live Codex path is an untrusted planning and narration boundary. The
default transport uses a fixed argument vector, `shell=False`, a read-only
Codex sandbox, a strict JSON envelope and a timeout. It passes structured
context as standard input; user text is never interpreted as a command.

`CodexLiveProvider` rejects scientific-authority fields such as Evidence,
EvidenceLevel, runs, bundles and engine results. `PlanValidator` then checks
Labs, experiments, allowlists, dependencies, input shapes, units, evidence
ceilings, claims and engine availability before the orchestrator can execute.

## Grounding

Live narration must reference recorded run/evidence IDs, use the recorded
status and evidence ceiling, and cannot introduce unrecorded numeric values.
Contradictory narration is returned as `NARRATION_GROUNDING_FAILURE`; it is
not persisted as scientific truth. The bounded Codex loop stops at a missing
experimental-validation level and never upgrades computational output.

## Existing scope

The web server serves a fixed static allowlist and rejects path traversal.
Engine adapters use argv lists, timeouts and path/hash checks. Source URLs are
rendered only for `http`/`https` schemes. User Knowledge imports remain
`REVIEW_REQUIRED` until human verification.

The preserved `Biolab/` tree still contains historical `shell=True` calls and
the preserved `formolecular/` tree retains its legacy model scripts. Neither
tree is in the Research OS web/service import graph and neither was modified
by this milestone.
