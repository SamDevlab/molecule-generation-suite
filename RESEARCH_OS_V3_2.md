# Research OS 3.2 — Live Codex Oracle Operations

Status: implemented on `research-os-v1.3`. The deterministic CI boundary and
the live operational boundary are intentionally separate.

## Operational status

| Boundary | Status | Meaning |
|---|---|---|
| Codex deterministic test provider | PASS | `CodexTestProvider` supplies repeatable structured planning for CI; it is not a scientific evidence provider. |
| Codex live Oracle | PASS | `CodexLiveProvider` uses the actual Codex session through the local `codex exec` bridge for planning and narration validation. |
| Live reasoning | VALIDATED | The non-CI acceptance harness exercises the real bridge, plan validation, execution, grounding and bounded-loop paths. |
| Scientific evidence provider | FALSE | Only registered Labs and engines create Evidence, Runs and Bundles. |
| External LLM API | NOT_REQUIRED_FOR_THIS_MILESTONE | No OpenAI SDK, API key or external model client is required for this integration. |
| Standalone web LLM | NOT_AVAILABLE | `STANDALONE_LLM_BRIDGE_NOT_IMPLEMENTED`; the web server consumes the configured provider boundary. |
| Plan validation | ENFORCED | Live output is typed, allowlisted, unit-checked, engine-checked and fail-closed before execution. |
| Grounding | ENFORCED | Narration may cite recorded IDs and limitations but cannot create values, evidence levels or scientific authority. |

## Boundary

```text
user message
  -> live Codex structured interpretation
  -> ResearchQuestion
  -> live Codex typed plan proposal
  -> PlanValidator + bounded repair
  -> ResearchOrchestrator
  -> registered Labs / real engines
  -> Evidence / Claims / Bundle / Ledger
  -> live Codex narration of recorded results
  -> narration grounding gate
  -> OracleAnswer + audit trace
```

The live model is a reasoning and narration component only. It never receives
authority to create or mutate Evidence, Runs, Bundles, Sources, datasets,
engine results or claims. The executor remains the source of truth.

## Live Codex bridge

The default transport is `CodexCliTransport`. It invokes the locally installed
Codex CLI using a fixed argument vector:

```text
codex exec --ephemeral --skip-git-repo-check --sandbox read-only \
  --color never --output-schema src/research_os/oracle/live_output.schema.json -
```

The implementation uses `subprocess.run(..., shell=False)` with a timeout and
passes a prompt as standard input. The strict transport envelope contains a
single string field, `result`, whose inner JSON is parsed again by the live
provider. Runtime headers are captured for audit; the validated environment
reported `codex-cli 0.152.1` and `gpt-5.6-luna`.

The bridge is local to the active Codex installation. It is not a standalone
web LLM service and it is not an external scientific API. If the CLI, schema,
runtime model identity or response contract is unavailable, the provider
reports that fact and does not silently fall back to fabricated results.

## Provider contract

| Provider | Mode | Deterministic | Production validation | Scientific evidence |
|---|---|---:|---:|---:|
| `CodexTestProvider` | `INTEGRATION_TEST` | true | false | false |
| `CodexLiveProvider` | `LIVE_ORACLE` | false | true | false |

Both providers implement structured planning methods. The live provider adds
runtime model/CLI audit metadata, session/question/plan IDs, prompt/response
digests, validation status, repair count and timestamps to the trace.

## Safety and grounding invariants

- Unknown Labs, experiments, tools, dependencies, units, engines and claim
  levels fail closed before execution.
- A missing engine is `INDETERMINATE`; downstream steps are `SKIPPED`.
- A live response containing `evidence`, `runs`, `bundle`, `engine_result` or
  equivalent scientific-authority fields is rejected with
  `LLM_OUTPUT_CANNOT_CREATE_SCIENTIFIC_EVIDENCE`.
- Narration references must resolve to recorded run/evidence IDs and cannot
  introduce unrecorded numeric values or a stronger evidence level.
- Knowledge retrieval contributes citations only; it never promotes a Lab
  result.
- The bounded Codex-driven loop stops at
  `EXPERIMENTAL_VALIDATION_REQUIRED` instead of repeating computation or
  claiming experimental validation.
- Typed `{"from_step": "..."}` inputs are resolved by the orchestrator to the
  completed upstream run's recorded request shape. Values still originate in
  the upstream Lab and remain in the immutable run lineage.

## Live acceptance suite

Run outside deterministic CI from the repository root:

```powershell
.\.venv\Scripts\python.exe tools\oracle\codex_live.py `
  --data-root .research-os-live-3.2 `
  --output .research-os-live-3.2\live-acceptance.json
```

The report stores each generated `ResearchQuestion`, `ResearchPlan`, validator
result, run payload, Evidence, Claims, answer and outcome. The suite covers:

| Case | Boundary exercised |
|---|---|
| LIVE-00 | live provider health and runtime bridge status |
| LIVE-01 | real Codex plan + RDKit molecular Evidence at E2 |
| LIVE-02 | real Codex plan + Cantera combustion and typed propulsion routing |
| LIVE-03 | unavailable Vina as `INDETERMINATE` with no execution |
| LIVE-04 | clinical/cure overclaim rejection |
| LIVE-05 | prompt-injection and E5 escalation containment |
| LIVE-06 | E4 request capped at the available evidence ceiling |
| LIVE-07 | Knowledge citation retrieval without evidence promotion |
| LIVE-08 | immutable continuation with `rerun_of` lineage |
| LIVE-09 | live ranking narration grounded in recorded values |
| LIVE-10 | real MoleculeLab workflow `FIRST_DIVERGENCE` |
| LIVE-11 | bounded loop stop at experimental-validation gap |
| LIVE-12 | controlled contradictory ranking narration failure |

This suite is deliberately not a GitHub Actions prerequisite: deterministic
CI must remain reproducible without a live model or a local Codex session.

## Engine truth in the validated environment

RDKit and Cantera were available in the local `.venv`; the live acceptance
path produced real molecular and combustion/ideal-nozzle computational
Evidence. The Cantera `gri30.yaml` mechanism supports the methane/hydrogen
cases used by the acceptance path; it does not imply support for every fuel
(for example, ethanol is not a species in this mechanism). AutoDock Vina and
Open Babel remain not configured, while materials engines remain dependent on
their optional local installations.

`Biolab/` and `formolecular/` remain preserved audit inputs. No main-branch
change, merge or force-push is part of this milestone.
