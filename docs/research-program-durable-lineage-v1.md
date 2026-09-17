# Research Program durable lineage v1

Research Programs coordinate a bounded scientific question across multiple
predeclared Campaigns. They do not execute Experiments directly, replace the
Campaign layer, or promote the Evidence Level.

```text
Research Program
       │
       ├── Campaign A
       │      ├── Experiment A1
       │      └── Experiment A2
       │
       └── Campaign B
              └── Experiment B1

Dataset Registry ─┐
Model Registry   ─┼→ Experiment/Campaign lineage
Ledger/Evidence  ─┘

All verified upward into Program lineage.
```

## Layers and identities

The static v1 contract is `research-os.program.protocol.v1+<hash>` and is
represented by `ResearchProgramProtocol`. It contains the scientific question,
declared Campaign Protocol references, the static dependency graph, limits,
failure policy, Campaign roles and the structural synthesis plan. All Campaign
Protocol identities are resolved before execution.

The following identities are intentionally separate:

```text
Program Protocol ID       = frozen scientific plan
Program Execution ID      = one concrete execution
Program Record ID         = durable execution record
Campaign Protocol ID      = child scientific plan
Campaign Execution ID     = child execution
Program Bundle ID         = final reference bundle
ResearchProgram.digest    = complete mutable snapshot integrity
```

`ResearchProgram.digest` remains compatible with the existing state machine. It
hashes mutable state such as status, progress and timestamps and must not be
interpreted as the scientific Program Protocol identity.

Operational fields such as local paths, SQLite paths, hostnames, timestamps,
durations, execution IDs and formatting are excluded from the Program Protocol
scientific hash. Scientific changes to a Campaign reference, dependency,
limit, role or synthesis plan change the Protocol ID.

## Static planning and execution

`DeclarativeProgramRunner.plan()` resolves every declared Campaign through the
existing `DeclarativeCampaignRunner`. It validates Campaign identities and
hashes, dataset/model requirements exposed by the Campaign plan, dependency
cycles, Campaign/run limits and retry policy. v1 is
`STATIC_PREDECLARED`; retry count is zero. It does not add Campaigns based on
observed results or metrics.

`DeclarativeProgramRunner.run()` creates an isolated execution root and frozen
Program/Campaign protocol documents. Each Campaign is delegated to the
existing Campaign runner, which in turn delegates to the Experiment Engine.
The Program layer never copies training, splitting, dataset verification,
model serialization or experiment comparison logic.

Each Program execution has its own root and durable SQLite store. Program
snapshots are mutable, while Campaign transition events are append-only.
Snapshot-plus-child-transition writes use one SQLite transaction. Existing
Program objects and stores remain readable; new tables are created with
`CREATE TABLE IF NOT EXISTS`.

## Limits, dependencies and failures

- `max_campaigns` and the sum of declared Campaign capacities are checked
  before the first child execution.
- `max_runs` counts Experiment runs reported by child Campaigns.
- `max_failures` and the declared failure policy are enforced without implicit
  retries.
- A failed independent Campaign may be followed by another independent
  Campaign while the failure limit permits it.
- A Campaign whose dependency failed is recorded as
  `SKIPPED_DEPENDENCY`, not as a hidden failure.
- A Campaign with no terminal state is invalid during verification.
- After `program_execution_started=true`, the declared Campaign set and
  resolved Protocol identities are frozen for that execution.

The existing `ResearchProgramController` remains the authority for immutable
resource limits, iteration accounting and the two-consecutive-no-progress
rule. Completion of a process does not by itself create scientific progress.

## Durable lineage and verification

The Program manifest references, rather than duplicates, child Campaign
execution records. The lineage is therefore:

```text
Program
  → Program Protocol
  → Program Execution
  → Campaign Protocol
  → Campaign Execution / Bundle
  → Experiment Protocol / Run
  → Dataset and Model Registry records
  → Evidence / Ledger / Bundle
```

Verification is structured and fail-closed. It checks the Program protocol and
execution hashes, declared versus observed Campaigns, Campaign protocol and
execution identities, Campaign bundle verification, terminal statuses,
dependency semantics, retry count, run/failure limits, durable snapshot
integrity, bundle hash and lineage references. First-loss examples include:

```text
PROGRAM_PROTOCOL_INVALID
PROGRAM_PROTOCOL_IDENTITY_MISMATCH
PROGRAM_CAMPAIGN_LIMIT_EXCEEDED
PROGRAM_RUN_LIMIT_EXCEEDED
PROGRAM_DEPENDENCY_CYCLE
PROGRAM_CAMPAIGN_PROTOCOL_MISSING
PROGRAM_CAMPAIGN_PROTOCOL_MISMATCH
PROGRAM_CAMPAIGN_EXECUTION_MISSING
PROGRAM_CAMPAIGN_VERIFY_FAILED
PROGRAM_UNDECLARED_CAMPAIGN
PROGRAM_RECORD_HASH_MISMATCH
PROGRAM_SNAPSHOT_DIGEST_MISMATCH
PROGRAM_LINEAGE_INCOMPLETE
```

Dataset and Model Registry byte/provenance checks remain the responsibility of
the child Campaign and Experiment verification gates. Program verification
requires those child gates to pass; it does not deserialize model artifacts or
reimplement registry verification.

## Bundle and knowledge boundary

`program-bundle.json` stores Program, Campaign, run, dataset, model and
evidence references plus the structural `KnowledgeGainAssessment`. It does not
copy all child raw artifacts into a new monolithic file. Negative results,
failed or skipped Campaigns, unresolved uncertainty and revised claims remain
visible in the Program record.

The default Program synthesis is structural and scientifically `UNASSESSED`.
The bundle remains `E2_COMPUTATIONAL`; multiple E2 Campaigns do not become a
higher Evidence Level, and Program completion does not imply hypothesis
support.

## CLI

```bash
research-os program plan program.yaml
research-os program validate program.yaml
research-os program run program.yaml --output programs/<execution>
research-os program verify programs/<execution>
research-os program inspect programs/<execution>
```

`plan`, `validate` and `inspect` do not execute child Experiments. `verify`
rechecks the persisted execution and child Campaign packages. A new output
root is required for every execution; an existing root is never overwritten.

## Compatibility and scope

The existing `ResearchProgram` and `ResearchProgramController` APIs remain
available, and historical Program/Campaign/Experiment records are not
rewritten. Domain-specific Campaign paths remain unchanged. Research Programs
are a coordination and provenance layer only; they do not bypass Campaigns,
perform adaptive post-result selection, or claim affinity, efficacy, biological
validity or clinical value.

Program reproduction is intentionally incremental: every child execution keeps
its normal `experiment-reproduce` compatibility. A full Program reproduction
command is a future bounded capability, not an implicit rerun mechanism.
