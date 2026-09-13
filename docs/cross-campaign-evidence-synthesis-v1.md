# Cross-campaign evidence synthesis v1

Cross-campaign synthesis evaluates evidence at the claim level. It is a
declared, post-execution analysis over verified Campaign bundles; it does not
run or rerun scientific work.

```text
Campaign A ── Evidence A ─┐
                          │
Campaign B ── Evidence B ─┼─→ Claim Synthesis
                          │       │
Campaign C ── Evidence C ─┘       ├─ Agreement
                                  ├─ Conflicts
                                  ├─ Claim status
                                  ├─ Limitations
                                  └─ Knowledge gain
```

## Declared synthesis plan

The Program Protocol may use `synthesis.mode: CLAIM_LEVEL` and declare each
claim before execution. A claim freezes its statement, minimum Evidence Level,
Campaign membership, required comparability dimensions and decision rule:

```yaml
synthesis:
  mode: CLAIM_LEVEL
  claims:
    - local_id: binding_improves
      statement: "Method X improves the declared recovery endpoint."
      minimum_evidence_level: E2_COMPUTATIONAL
      campaigns: [baseline, validation]
      comparability:
        required_dimensions: [endpoint, metric, threshold]
      decision_rule:
        type: DESCRIPTIVE_AGREEMENT
```

Changing any scientific field changes the Program Protocol identity. A claim
cannot be added after a Program Execution has started. Synthesis input is a
normalized projection of sealed Campaign evidence and is itself hashed and
persisted; it is not a replacement for the Campaign bundle.

## Evidence matrix and contribution states

Every Campaign named by a claim must appear in the matrix. Each member is
represented as `SUPPORTS`, `CONTRADICTS`, `NEUTRAL`, `INDETERMINATE`,
`NOT_COMPARABLE` or `UNAVAILABLE`. A failed or skipped Campaign is unavailable,
not negative evidence. An analysis failure is indeterminate, not a rejection.

Available evidence IDs must resolve to the verified Campaign bundle, and the
Campaign execution ID, bundle ID and bundle hash must match the Program
execution. Evidence imported from an undeclared Campaign or an unverified
bundle is rejected fail-closed.

The engine reuses `EvidenceAgreementAssessment` and
`EvidenceAgreementStatus`. It does not implement majority vote or average
metrics:

- `CONSISTENT`: comparable qualified contributions agree;
- `PARTIALLY_CONSISTENT`: the available contributions agree but a declared
  member is unavailable or indeterminate;
- `CONFLICTING`: comparable contributions support incompatible directions;
- `NOT_COMPARABLE`: required dimensions are missing or differ;
- `INSUFFICIENT_EVIDENCE`: no qualified conclusion can be made.

Conflicts retain the claim, Campaigns and evidence IDs involved. Negative
results remain in `negative_results`; unavailable and indeterminate records
remain in their own matrix entries.

## Claim status and revisions

The existing `ScientificClaim` and `ClaimStatus` contracts are reused. A claim
is `SUPPORTED` only when the declared rule is satisfied, all declared members
are qualified and comparable, and no unresolved conflict remains. A claim is
`REJECTED` only under an explicit `PREDECLARED_DIRECTION` rule. Otherwise the
claim remains `INSUFFICIENT_EVIDENCE`; lack of support is not silently turned
into proof that a hypothesis is false.

When a declared prior claim changes status or evidence, the engine emits the
existing append-only `ClaimRevision`. The predecessor is preserved and the
revision carries its reason, prior evidence, current evidence and synthesis
lineage. Historical claims are never overwritten.

## Evidence Level boundary

The synthesis records `strongest_supported_level` as the maximum level among
qualified contributing evidence. Levels are not added or promoted:

```text
E1 + E1 = at most E1
E2 + E2 + E2 = at most E2
E1 + E3 = strongest available E3, not automatic E3 claim support
```

The Program remains `E2_COMPUTATIONAL` in the current Research OS contract.
Aggregation does not create experimental, biological, clinical or affinity
truth. Claim-level minimums still have to be met by qualifying evidence.

## Durable synthesis record

The synthesis identity is separate from all other identities:

```text
Program Protocol ID
Program Execution ID
Program Synthesis ID = research-os.program.synthesis.v1+<hash>
Program Bundle ID
Campaign Execution IDs / Bundle IDs
Evidence IDs
```

The synthesis hash depends on the frozen Program Protocol, Program Execution,
synthesis engine, claim outcomes, Campaign bundle identities/hashes, evidence
IDs, contribution states and comparability dimensions. It excludes timestamps,
paths, hostnames, SQLite locations and JSON formatting.

`program-synthesis.json` is persisted alongside the Program manifest. The
`ResearchProgramStore` adds an append-only `program_syntheses` table. Repeated
assessment preserves the prior record under `syntheses/` and records the
history instead of silently deleting it. The Program Bundle references the
synthesis ID/hash, claim IDs, revisions, agreement assessments, conflicts and
negative results without copying raw Campaign artifacts.

## Verification and CLI

Before synthesis, the Program execution and every completed Campaign must
verify. Synthesis verification then checks the input schema, exact Program
Execution linkage, exact declared Campaign membership, Campaign bundle hashes,
evidence IDs, claim matrix, synthesis identity, durable store record, bundle
linkage and Evidence Level boundary. Representative first-loss codes are:

```text
PROGRAM_SYNTHESIS_INVALID
PROGRAM_SYNTHESIS_IDENTITY_MISMATCH
PROGRAM_SYNTHESIS_INPUT_MISSING
PROGRAM_SYNTHESIS_UNDECLARED_CAMPAIGN
PROGRAM_SYNTHESIS_UNDECLARED_CLAIM
PROGRAM_SYNTHESIS_EVIDENCE_MISSING
PROGRAM_SYNTHESIS_EVIDENCE_MISMATCH
PROGRAM_SYNTHESIS_LEVEL_INFLATION
```

```bash
research-os program synthesize programs/<execution>
research-os program verify programs/<execution>
research-os program inspect programs/<execution>
```

`program synthesize` consumes persisted evidence only. It never executes an
Experiment, reruns a Campaign, trains a Model, downloads a Dataset, changes a
parameter or invokes docking.

## Compatibility and scientific scope

Historical Program executions without a formal synthesis remain valid and
`UNASSESSED`. Existing Evidence, Claims, Campaigns, manifests and runs are not
rewritten. This feature adds a bounded synthesis layer over verified lineage;
it does not reinterpret historical docking results or create a universal
Program score.
