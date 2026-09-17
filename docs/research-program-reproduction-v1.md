# Research Program reproduction v1

Research Program reproduction recreates a verified, static Program execution
tree in a new root. It is a provenance operation, not a shortcut for copying
historical outputs and not an adaptive research workflow.

```text
frozen Program Protocol
        |
        v
new Program Execution
        |
        +--> new Campaign Executions
                 |
                 +--> new Experiment Runs
                         |
                         +--> verified Dataset/Model provenance
        |
        +--> recalculated Program synthesis
```

## Contract

`program reproduce <source-root> --output <new-root>` requires the source
Program to verify successfully before any child execution starts. The source
root is read-only. Its complete file tree is hashed before and after the
operation; a mutation is a first loss rather than a best-effort result.

The reproduction delegates to `DeclarativeProgramRunner`, which delegates to
the existing `DeclarativeCampaignRunner` and Experiment Engine. The Program
layer never executes an Experiment directly, never retries a child implicitly,
and never changes a frozen protocol after the new execution starts.

The source and reproduced executions retain the same scientific Program
Protocol identity. They receive different Program Execution, Campaign
Execution, Experiment Run, Bundle, and (when present) Synthesis identities.
The reproduction record explicitly reports scientific equivalence, operational
identity differences, and scientific divergence.

## Identity boundaries

```text
Program Protocol ID       = frozen scientific plan
Program Execution ID      = one concrete execution
Campaign Protocol ID      = frozen child campaign plan
Campaign Execution ID     = one concrete campaign execution
Experiment Run ID         = one concrete child run
Synthesis ID               = synthesis of the reproduced execution
Reproduction ID            = durable comparison record
```

The reproduction identity excludes absolute roots, timestamps, and execution
IDs. Consequently, equivalent reproductions may have the same reproduction
identity while their operational records remain distinct. Scientific result
hashes and dataset/model identities are compared separately.

## Fail-closed gates

The source must pass Program, Campaign, Experiment, Dataset Registry, Model
Registry, and implementation provenance verification. External dataset bytes
are re-hashed before execution; registry records are verified through the
Dataset Registry. Missing or mutated source material blocks reproduction.

After execution, the reproduced Program and its recalculated synthesis must
verify. The source tree must still match its preflight snapshot. The durable
record is append-only in `ResearchProgramStore`; equal hashes are idempotent,
while conflicting records are rejected.

Important first-loss classes include:

- `PROGRAM_REPRODUCTION_SOURCE_INVALID`
- `PROGRAM_REPRODUCTION_SOURCE_INCOMPLETE`
- `PROGRAM_REPRODUCTION_SOURCE_MUTATED`
- `PROGRAM_REPRODUCTION_DATASET_IDENTITY_MISMATCH`
- `PROGRAM_REPRODUCTION_IMPLEMENTATION_MISMATCH`
- `PROGRAM_REPRODUCTION_PROTOCOL_MISMATCH`
- `PROGRAM_REPRODUCTION_CAMPAIGN_SET_MISMATCH`
- `PROGRAM_REPRODUCTION_SYNTHESIS_DIVERGENCE`
- `PROGRAM_REPRODUCTION_RESULT_DIVERGENCE`

An unavailable or failed child is preserved as such. It is not silently
converted into a scientific negative result, and it is never retried by the
Program reproduction layer. Synthesis remains at the evidence level supported
by the contributing Campaign evidence; reproduction does not promote Evidence
Level.

## Synthesis and compatibility

If the source Program contains a frozen synthesis input, the reproduction
constructs a new input from the reproduced Campaign bundles and calls the
existing `synthesize_program` implementation. It does not copy the source
synthesis record. Claim-level results, conflicts, unavailable evidence, and
negative results are therefore re-evaluated from the new verified lineage.

Scientific equivalence requires the same frozen Program Protocol, compatible
Campaign/Experiment identities, matching verified Dataset/Model provenance,
matching scientific result hashes, and matching synthesis projections. Byte
differences in operational manifests or artifacts are reported separately from
scientific divergence.

## CLI

```bash
research-os program reproduce <program-root> --output <new-root>
research-os program reproduction-verify <reproduction-root>
research-os program reproduction-inspect <reproduction-root>
```

Verification and inspection never run Campaigns or Experiments. A historical
Program without a reproduction record remains a valid historical Program; it
is not rewritten or retroactively assigned a reproduction identity.
