# Research OS v1.5 — Persistent Research Ledger

Research OS v1.5 adds a persistent, SQLite-backed index over the immutable
ResearchBundles produced by v1.4. The ledger is an operational index: the
bundle directory remains the source of truth and the index can be rebuilt at
any time with `rebuild-index`.

## What is indexed

`RunRegistry` records run identity, bundle hash/path, lifecycle status, sealed
state, lab/experiment, workflow and plan IDs, timestamps, git/environment
identity, `FIRST_LOSS`, tags, datasets, models, claims, evidence, and lineage.
Claims and evidence retain their IDs, levels, kinds, payloads, and provenance
IDs so a result can be traced back to its bundle and source records.

The SQLite schema is versioned and migrated transactionally. It enables WAL,
foreign-key enforcement, a busy timeout, and indexes for status, lab,
workflow, date, datasets, claims, evidence, tags, and lineage. A registration
with the same `run_id` and bundle hash is `ALREADY_REGISTERED`; a different
hash fails with `LEDGER-RUN-CONFLICT-001`.

```python
from research_os.ledger import RunRegistry

registry = RunRegistry("research-ledger")
registration = registry.register_run("runs/PLAN-EXAMPLE")
recent = registry.search_runs(status="SEALED", lab="MoleculeLab", limit=20)
lineage = registry.get_lineage(recent[0].run_id)
verification = registry.verify_ledger()
registry.close()
```

`remove_index_entry` removes only SQLite rows. It never removes the bundle.
`rebuild_index(bundle_root)` scans bundle metadata, indexes valid bundles, and
does not index bundles whose verification status is `FAIL`. Bundles that are
valid but externally indeterminate remain visible with that condition.

## Lineage and scientific dependency

The ledger distinguishes temporal metadata from scientific dependency. A
timestamp never creates an edge. Explicit `RunDependency` edges support
`depends_on`, `derived_from`, `rerun_of`, `supersedes`, and
`consumes_output_of`. Ancestor/descendant queries use those edges, and cycle
attempts fail with `LEDGER-LINEAGE-CYCLE-001`.

## Workflows and reproducibility

Registering a `PlanRun` indexes the workflow and its individual step runs.
`rerun_workflow` reconstructs the materialized plan, creates a new workflow and
step run IDs, records lineage to equivalent runs, recaptures the environment,
and carries dataset manifests forward for hash revalidation.

`compare_workflows` compares plan topology, inputs, config, dataset hashes,
code commit, environment hash, and result values (gates and evidence payloads),
not only status. It persists `FIRST_DIVERGENCE` with the first step, rule,
reason, and before/after values. Results are `REPRODUCED`,
`REPRODUCED_WITH_ENVIRONMENT_CHANGE`, `DIVERGED`, `NOT_COMPARABLE`, or
`INDETERMINATE`. `workflow_regressions` classifies explainable result, gate,
dataset, environment, and artifact changes.

## Artifact packing

```python
ResearchBundle.create(
    run,
    "runs",
    artifacts={"metrics.json": "outputs/metrics.json"},
    pack_artifacts=True,
)
```

Packed files are stored content-addressably below
`artifacts/sha256/<prefix>/<sha256>`, with an artifact index containing the
original path, size, and digest. The original file may be removed after
packing. Executable and engine binaries are rejected by the packing boundary;
engine availability remains an environment fact, not a bundled executable.

## CLI

```text
research-os runs list --root research-ledger
research-os runs search --root research-ledger --lab MoleculeLab --tag golden
research-os runs show RUN-...
research-os runs verify RUN-...
research-os runs rebuild-index runs
research-os runs lineage RUN-...
research-os runs compare RUN-ORIGINAL RUN-RERUN

research-os workflows list --root research-ledger
research-os workflows show PLAN-...
research-os workflows rerun PLAN-... --output reruns
research-os workflows compare PLAN-A PLAN-B
research-os workflows regressions PLAN-A PLAN-B
research-os ledger verify --root research-ledger
research-os export json --root research-ledger --output ledger.json
```

All ledger operations emit structured JSON log records through the existing
`StructuredLogger`. Query values are parameterized; `order_by` is restricted
to a fixed allowlist.

## Golden coverage and limitations

The v1.5 tests cover a PASS workflow, deterministic rerun, deliberate
indeterminate/skipped execution, a deliberate result divergence,
`FIRST_DIVERGENCE`, dataset/environment comparison, claims/evidence/provenance
traces, rebuild, retention, rollback, cycle protection, artifact packing, and
lightweight pagination. The index intentionally does not replace the bundle,
does not duplicate the ML model registry, and cannot make a missing external
dataset or unavailable engine determinate. Legacy `Biolab/` and
`formolecular/` remain untouched. The next natural milestone is richer
cross-project retention/replication and a first-class external dataset
resolver.
