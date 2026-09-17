# APODOCK-001 v1.0.2 postmortem

## Scope and preservation rule

This postmortem was performed after PR #32 was merged and uses only the
committed APODOCK-001 v1.0.2 evidence. No Vina process was started, no case
was rerun, and no file below `runs/apodock001-v1.0.2/` was rewritten.

The v1.0.2 historical result remains unchanged.

Historical identities:

- protocol: `research-os.apodock001.protocol.v1.0.2+aa40517362e14795`
- protocol hash: `aa40517362e14795a9ea4747b632fab81b2fc1f5bb49e4c880d9ad38699de03c`
- input bundle: `research-os.apodock001.input-bundle.v1+4be4265fa5917645`
- planned run: `research-os.apodock001.planned-run.v1+ff217589e517ab64`
- final run: `research-os.apodock001.run.v1+1797487357db1db1`
- analysis engine: `research-os.apodock001.analysis.v1+25ebfa66ecace1dd`
- raw-results seal: `a57ca576e170f09a6768217f07d9965cf23cf18faa58be423a703816463482e1`
- evidence bundle: `c062d259edf170235654967c0057aaffe0ec19066d25af520ea440e42064666b`

## Historical closeout

PR #32 was reviewed at head
`6f7981b15ff8777aa31c77b935e7cd52a1d67480` and merged with head-SHA
protection. The merge commit is
`2860a8184812b8e40e2153a0e76420c8d482c25d`, which is the new
`research-os-v1.3` head.

The diff contained 429 files, all under the historical run directory. The
protocol and frozen input bundle had zero diff. The nine raw PDBQT outputs
matched the declared hashes in the seal; APD-006 correctly had no raw pose
file. Case order was APD-001 through APD-010 with no duplicate attempt record,
and all commands retained the frozen seed, CPU, exhaustiveness, mode count,
boxes, and no `energy_range`.

The historical result is:

- attempts: 10/10;
- completed: 9/10;
- execution failures: 1;
- determinate analyses: 7;
- indeterminate analyses: 2;
- primary recovery: 0/7 at `<= 2.0 Å`, mean 5.174 Å, median 5.606 Å;
- secondary recovery: 0/7 at `<= 2.0 Å`, mean 3.557 Å, median 3.324 Å.

The v1.0.2 primary and secondary vectors are not recomputed or replaced by
this document.

## Evidence and seal classification

The original `raw-results-seal.original.json` is preserved byte-for-byte.
The derived `raw-results-seal.json` differs semantically only by the addition
of the missing `protocol_hash`. Protocol ID, run ID, all raw output hashes,
the historical raw-results seal SHA, and `SEALED` status are unchanged. The
repair is therefore classified as a provenance-metadata repair, not a new
seal and not a new run. The original seal SHA remains the authoritative
historical identity.

The root cause is in the historical execution adapter: it wrote
`raw-results-seal.json` without copying `self.plan.protocol_hash`, even though
the run manifest contained it and the analysis gate required it. The future
contract in `apodock001_future.py` makes protocol ID, protocol hash, planned
run ID, final run ID, raw output hashes, schema, and status mandatory.

## APD-006 — execution

The case was attempted once. The recorded runtime was approximately 901.5 s;
the adapter used `subprocess.run(..., timeout=900.0)` and recorded
`returncode=-1`, no raw-output hash, and a failed case. Vina stdout shows that
the grid was computed and that docking progressed through the progress bar to
the recorded termination point. stderr is empty. There is no chemical error
message, no Docker error, and no retry.

Classification: `ADAPTER_SUBPROCESS_TIMEOUT`, confidence HIGH. This is an
operational timeout, not evidence that Vina crashed or that the ligand failed
chemically. The future timeout classifier preserves partial stdout/stderr,
records the timeout explicitly, and fixes retry count at zero; it does not
rerun the case.

## APD-007 — representation

Vina completed and returned 20 models. The historical analysis converted the
first model to an SDF, but RDKit sanitization failed at the exact conversion
boundary: Open Babel wrote a tetravalent nitrogen with formal charge zero.
RDKit reported `Explicit valence for atom #1 N, 4, is greater than permitted`.
The raw PDBQT contains the coordinate and atom graph information; this is not
a Vina execution failure.

`postmortem/APD-007-diagnostic-analysis.json` applies a future, narrow repair
to the already-derived representation: remove explicit hydrogens, match the
heavy-atom graph to the frozen reference, copy the frozen formal charge,
sanitize, and preserve all coordinates. The diagnostic same-frame RMSD is
8.846 Å, but it is explicitly `POSTMORTEM_DIAGNOSTIC_ONLY` and does not alter
the historical `POSE_CONVERSION_FAILED`, the 0/7 denominator, or any raw
file. No rigid fit, translation, or rotation is used.

## APD-010 — reference policy

APD-010 remains `REFERENCE_COORDINATES_INCOMPLETE`: the BEM+MAV execution
graph has 25 heavy atoms while the experimental mapping supplies 24. No
coordinate was fabricated and no generated conformer was promoted to an
experimental reference.

## SDF byte-level determinism

The committed determinism check records identical raw hashes, derived PDBQT
bytes, scores, mappings, metrics, statuses, and aggregation, while Open Babel
derived SDF bytes differ between analyses. A direct Open Babel diagnostic also
shows a timestamp-like `OpenBabel...3D` header, which is operational metadata
and is not a scientific coordinate or graph change. The future scientific pose
identity therefore hashes the source raw hash, adapter identity, canonical
graph identity, explicit reference-atom mapping, formal charges, and rounded
coordinates—not the derived SDF bytes or property ordering.

## Scientific diagnostics

The complete per-case matrix is in
`postmortem/apodock001-v1.0.2-diagnostic-matrix.json` and its compact Markdown
rendering. It was computed in temporary normalized copies where necessary to
avoid Windows CRLF checkout conversion; no historical file was modified.

### Box coverage

All mapped transformed reference atoms for APD-001 through APD-010 were inside
their frozen boxes and classified `BOX_COVERAGE_OK`. The minimum axis margin
was 6.0 Å or greater. The frozen box policy is therefore not implicated by
an atom lying outside the search region.

### Sampling and ranking

For all seven determinate cases, the best same-frame RMSD among the 20 returned
poses remained above 2 Å. This is evidence against a purely ranking-only
explanation: no near-threshold pose was present for the evaluator to rank
first. The best pose ranks were 5, 15, 12, 18, 5, 15, and 10 across the
determinate cases. Pose-pair spreads were several Å in every determinate case,
showing that the output was not a set of byte-identical poses; the pairwise
metric is a separate predicted-to-predicted diagnostic with no fitting.

### Score versus RMSD

Per-case Pearson and Spearman associations are reported in the matrix and are
descriptive only. They are mixed in sign and magnitude across seven cases.
This does not support a strong claim that Vina generated near-reference poses
and only ranked them incorrectly.

### Receptor apo/holo geometry

The global holo-to-apo C-alpha transform RMSDs range from approximately 2.10
to 7.14 Å, and the local pocket displacement diagnostics are likewise
non-trivial. This makes rigid-apo receptor mismatch a plausible contributor,
especially for the larger structural shifts, but it is not isolated
causality: the benchmark has seven determinate cases and multiple interacting
sources of error.

### Ligand preparation

The frozen chemistry gate, prepared-artifact hashes, formula/heavy-atom
contracts, and APD-010 adapter identity are internally consistent. No silent
chemistry change was found. Independent conformer generation remains a
possible scientific factor, but the existing evidence does not identify it as
the cause.

## Hypothesis ranking for v1.1

| Hypothesis | Evidence | Evidence against | Confounding/cost | Decision |
|---|---|---|---|---|
| Rigid apo receptor mismatch | large apo/holo and pocket displacements; boxes cover reference | no causal isolation; flexible/ensemble receptor would be a major change | high leakage and implementation cost if receptor states are selected post hoc | plausible alternative |
| Insufficient search sampling | all best-of-20 RMSDs remain >2 Å; broad pose spread; weak score/RMSD association | broad spread also means search is not obviously collapsed; APD-006 already timed out | moderate runtime cost; directly testable with one pre-registered search policy | selected v1.1 hypothesis |
| Ranking/scoring limitation | best pose is often not pose 1 | no near-threshold pose appears in any 20-pose set | changing scoring would confound engine behavior | not selected |
| Ligand preparation | independent conformer is a possible mismatch source | chemistry and preparation provenance are consistent; no direct artifact found | changing protonation/conformer policy would be a large confound | not selected |

The selected v1.1 hypothesis is deliberately modest:

> Under the same frozen cohort, inputs, boxes, receptor preparation, ligand
> preparation, Vina binary, seed, CPU, scoring function, and evaluator, a
> single higher-exhaustiveness search may recover a lower-RMSD pose because
> the v1.0.2 search budget did not sample the relevant basin.

This is a prospective test, not a claim that sampling is the proven cause.

## Future-facing changes only

| Change | Category | Scientific? | Rationale | Expected effect |
|---|---|---:|---|---|
| Require protocol hash in future raw seals | provenance | no | close the historical omission | fail closed before analysis |
| Reference-guided APD-007 pose normalization | analysis representation | no | preserve graph/charge semantics when Open Babel omits formal charge | convert valid future representations without changing coordinates |
| Scientific pose identity independent of SDF bytes | provenance/analysis | no | remove timestamp/property serialization from identity | stable rerun identity |
| Explicit timeout classifier and zero retries | infrastructure | no | distinguish adapter timeout from Vina failure | preserve evidence and prevent rerun |
| v1.1 exhaustiveness 32 with one 1800 s timeout | scientific docking protocol | yes | one controlled test of the sampling hypothesis | increase search budget without changing other scientific controls |

No future-facing fix is applied to the historical run directory.
