# Declarative Campaign Orchestration v1

Research OS campaigns coordinate science; they do not replace the Experiment
Engine. Version 1 adds an opt-in static campaign protocol that declares a
finite set of independent child experiment protocols before execution.

```text
Research Program
        ↓
Research Campaign
        ↓
Campaign Protocol
   ┌────┼────┐
   ↓    ↓    ↓
  E1   E2   E3
   ↓    ↓    ↓
Dataset / Model Registries
   ↓    ↓    ↓
 Run Manifests + Evidence
        ↓
 Campaign Analysis
        ↓
 Campaign Bundle
```

## Boundaries and identities

The campaign protocol identity is
`research-os.campaign.protocol.v1+<hash>`. It is computed from the research
question, declared child protocol scientific identities, dependencies, limits,
failure semantics, and the preregistered multiplicity plan. Paths, registry
roots, timestamps, hostnames, YAML/JSON formatting, and run duration are
operational metadata and do not change this identity.

The campaign execution identity, child Experiment Engine execution identities,
campaign record identity, and campaign bundle identity remain separate. A
child keeps its own protocol, manifest, dataset references, model references,
implementation identity, result, and evidence. The campaign manifest stores
references and status; it does not copy raw child artifacts.

## Static planning

`DeclarativeCampaignRunner.plan()` resolves every child protocol, verifies
declared Dataset Registry references, validates safe local IDs, checks
`max_runs`, and topologically sorts the explicit dependency DAG. Cycles,
missing children, invalid protocols, and registry failures are blocked before
the first child run. `retry_count` is required to be zero in v1.

The runner snapshots the resolved child protocols into the execution package
with operational paths made explicit before `campaign_execution_started` is
set. A campaign cannot add, remove, or mutate its scientific child plan after
that boundary. A second run uses a new output root and never overwrites the
first execution.

## Failure isolation

Each child has a separate output root, status, attempt record, and first-loss
field. Independent children may continue under `continue_independent` until
`max_failures` is reached. A dependent child becomes
`SKIPPED_DEPENDENCY`, not a false execution failure. No failed child is
silently retried, removed, or repaired using a post-result parameter change.

Execution completion is separate from scientific support. A campaign with
completed children has `scientific_status: UNASSESSED` until a declared
analysis establishes an allowed conclusion.

## Registries and provenance

Before a child that declares a Dataset Registry dependency runs, the durable
dataset record, scientific dataset identity, record identity, and artifact
bytes are verified. The resulting references are retained in the campaign
execution record and the child run verifies them again. Opt-in child model
registration remains the Model Registry's responsibility; the campaign bundle
retains model record and artifact references without deserializing models.

Child `verify`, `inspect`, `reproduce`, and `compare` continue to be supplied
by the Experiment Engine. Campaign analysis calls `experiment-compare` only
for preregistered compatible pairs and preserves `NOT_COMPARABLE` outcomes.

## Multiplicity and claims

Every comparison belongs to a declared analysis family. The v1 fixture and
runner support `DESCRIPTIVE_ONLY`; this explicitly emits no multiplicity-
adjusted inferential claim. All declared comparisons are retained in the
machine-readable analysis manifest, so a campaign cannot silently select one
favorable result from a larger family. An inferential campaign requires a
separate frozen statistical contract and is rejected by this version.

Campaign coordination does not increase Evidence Level. The default summary
remains `E2_COMPUTATIONAL`, and successful execution is not a claim that a
hypothesis is supported.

## Persistence and verification

`DeclarativeCampaignStore` uses SQLite tables created with
`CREATE TABLE IF NOT EXISTS`, alongside the historical `CampaignStore`
tables. Snapshots are replaceable coordination state, while child status
transitions and events are append-only. The execution package contains a
campaign protocol document, execution plan, campaign manifest, child runs,
analysis manifest, and bundle references. `campaign verify` checks the record
hash, protocol-document hash, plan hash, declared-versus-observed children,
child run packages, multiplicity disclosure, and the Evidence boundary.

The existing `ResearchProgram` model and controller remain the program-level
coordination abstraction. This change does not add a second program layer or
make a Research Program execute experiments directly; a future integration
can reference these durable campaign executions.

## CLI

```bash
research-os campaign plan campaign.yaml
research-os campaign validate campaign.yaml
research-os campaign run campaign.yaml --output campaigns/execution-001
research-os campaign verify campaigns/execution-001
research-os campaign inspect campaigns/execution-001
```

The fixture used by the test suite is fully offline and uses small declarative
regression protocols. No docking, network access, or heavy benchmark is part
of campaign orchestration v1.
