# Research OS 4.0 — scientific validation release

Research OS 4.0 is a validation release over the v3.9–v3.12 contracts. Its
claim under test is:

> Research OS behaves as a scientifically bounded, reproducible,
> evidence-aware autonomous research system.

The benchmark is fail-closed. Codex Live proposes questions and produces
grounded narration only; Labs, registries, Evidence, Claims, Decisions,
bundles and the Ledger remain Research OS responsibilities.

## Gate

The release requires PASS artifacts for v3.9, v3.10, v3.11 and v3.12, 100
fixed/systematic cases, 30 new Codex-generated cases, 15 repeated-question
groups, 15 paraphrase groups, 15 bilingual groups, 20 reproductions, 50 stress
tests, the A/B/C autonomous exam, its 20 follow-ups, scientific/security
audits, package validation and green remote CI.

Run the live validation with:

```text
python tools/benchmark/master_validation_v40.py \
  --root .research-os-live-4.0 \
  --output .research-os-live-4.0/master-validation.json \
  --ci-green
```

The optional replay flags are only for re-auditing an already completed live
run; replayed output is explicitly marked in the artifact and does not become
new scientific evidence.

## Scientific boundaries

- E1 remains ML, E2 remains computational, E3 remains physics simulation.
- Docking remains E2 and cannot become affinity, efficacy or safety.
- Cantera remains E3 and cannot become an experiment.
- OOD, uncertainty, units, species and conditions remain explicit.
- Dependent evidence is not counted as independent confirmation.
- Missing external measurements produce `NO_DECISION`, not invented data.
- Conversation, source text and user/authority pressure cannot override the
  Ledger or typed tool policy.

The machine-readable PASS record is
`.research-os-live-4.0/master-validation.json`; companion artifacts contain
the final exam, reproduction matrix and invariant audit.
