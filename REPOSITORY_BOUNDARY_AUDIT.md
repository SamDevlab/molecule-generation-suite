# Repository Boundary Audit

Date: 2026-09-03

## Scope

The Oracle integration belongs to `molecule-generation-suite` (Research OS). It
does not belong to `S3 OS`, whose scope remains the operating-system installer,
boot, kernel, runtime and proof chain.

| Repository | Root | Branch | Boundary result |
| --- | --- | --- | --- |
| Research OS | `C:\Users\samue\Desktop\Bio\molecule-generation-suite` | `research-os-v1.3` | Canonical Oracle integration target |
| S3 OS | `C:\Users\samue\Desktop\S3 OS` | `main` | No Research OS modules retained |

## Evidence and provenance

The following S3 paths were absent from its `HEAD` and were untracked in the
working tree, so they were classified as newly introduced misplaced Oracle
artifacts:

- `src/research_os/`
- `tools/research/`
- `tests/test_codex_oracle.py`
- `docs/research-oracle.md`
- `pytest.ini` (only configured the misplaced Python test package)

Before removal, the complete set was copied to:

`C:\Users\samue\AppData\Local\Temp\s3-os-research-boundary-backup-20260903-125759`

The S3 OS's existing dirty changes, installer files, boot/runtime files,
proof artifacts and unrelated user files were not cleaned or reset.

## Canonical Research OS integration

The integration reuses the existing abstractions rather than adding parallel
modules:

- `research_os.oracle.provider.LLMProvider` now also has `CodexTestProvider`.
- `research_os.oracle.planner.OraclePlanner` performs structured parsing,
  question-aware validation and at most one conservative repair attempt.
- `research_os.oracle.validator.PlanValidator` remains the fail-closed plan
  gate, including allowlists, dependency cycles, units, engine readiness,
  claim ceilings and evidence requirements.
- `research_os.orchestration.ResearchOrchestrator` remains the only execution
  runner and preserves dependency order, `FIRST_LOSS` and downstream `SKIPPED`.
- `research_os.ledger.RunRegistry` remains the only persistent ledger.
- `research_os.service.OracleService` now connects ask -> job -> typed question
  -> typed plan -> validation -> orchestration -> grounded answer, with bundle
  and Ledger persistence when configured.
- Existing Knowledge OS retrieval is citation-only; it cannot increase the
  evidence level of computational results.

`CodexTestProvider` is local and structured only. Its metadata is:

```text
provider=CODEX_TEST
mode=INTEGRATION_TEST
external_api=false
scientific_evidence_provider=false
production_llm=false
```

The six canonical scientific evidence levels are `E0_HEURISTIC`, `E1_ML`,
`E2_COMPUTATIONAL`, `E3_PHYSICS`, `E4_CURATED_EXPERIMENTAL` and
`E5_VALIDATED_EXPERIMENTAL`. There is no `E3_CURATED`. The existing
`TEST_SYNTHETIC` marker is limited to test-fixture/dataset bookkeeping and is
not treated as a scientific ranking level.

## Required safety assertions

- RDKit/MoleculeLab output is E2 computational.
- Curated source retrieval is citation/provenance only.
- Docking cannot be narrated as cure, efficacy, safety or clinical proof.
- Missing Cantera produces `INDETERMINATE`, materialized `FIRST_LOSS` and
  downstream `SKIPPED` steps.
- OOD candidates are excluded from ranking rather than numerically penalized.
- Free text and malformed structured output never enter execution.
- Bundles are sealed and tampering is detected; the Ledger can rebuild its
  index from bundles.
- Legacy files remain preserved and are audited read-only through the existing
  v1.8 legacy package.

## Validation record

- Research OS: `py -3.11 -m pytest -q` -> **124 passed**.
- Research OS: `py -3.12 -m pytest -q` -> **124 passed**.
- Research OS: `py -3.11 -m compileall -q src` -> **PASS**.
- Research OS: `py -3.12 -m compileall -q src` -> **PASS**.
- Research OS: `git diff --check` -> **PASS**.
- Research OS static scan: forbidden `E3_CURATED`, `E4_EXPERIMENTAL` and
  `E5_CLINICAL` identifiers -> **none**; safety wording in guards and legacy
  negative assertions is intentional.
- S3 OS after cleanup: `py -3.11 -m pytest -q` -> **11 passed, 4 skipped**;
  skips are the pre-existing Windows-only shell/WSL functional boundary.
- S3 OS after cleanup: no `src/research_os`, Oracle, Codex provider or related
  imports remain.

Cantera, Vina and VM/ISO tooling are not required for the supported molecule
gate; the combustion scenario deliberately records missing Cantera as
`INDETERMINATE` with downstream skips. No push was performed for either
repository.
