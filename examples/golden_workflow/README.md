# Golden workflow

This fixture demonstrates the Research OS v1.4 path from a small versioned CSV through Dataset Registry, EnvironmentManifest, an explicit Fuel → Combustion → Thermal → Propulsion plan, evidence, claim, sealed ResearchBundle, and verification.

Use `--mode stub` for a deterministic test fixture. Its evidence is explicitly `TEST_SYNTHETIC` and must not be interpreted as physics or experiment. Use `--mode real` to exercise installed engines; missing Cantera remains `INDETERMINATE` and descendants are `SKIPPED`.

```text
python examples/golden_workflow/run.py --mode stub
python examples/golden_workflow/run.py --mode real
```
