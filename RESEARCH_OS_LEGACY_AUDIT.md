# Current legacy audit — molecule-generation-suite

Audit target: current `main` branch before Research OS migration.

## formolecular/g_oraculo_farma.py

Observed migration issues:

1. `Score_QED` is trained as an XGBoost target while the feature matrix already includes multiple descriptors directly involved in drug-likeness characterization (`Peso_Molar`, `LogP`, `TPSA`, FractionCSP3, rotatable bonds, aromatic rings, H donors/acceptors). In Research OS, QED belongs in the deterministic RDKit calculation path unless a separate surrogate use case is explicitly justified.
2. R² is displayed as a percentage of “clinical reliability”. Research OS treats R² as a regression metric, not clinical confidence.
3. Random `train_test_split` is useful as a baseline but is not enough to demonstrate chemical extrapolation. Future model protocols need scaffold/cluster/source/external split options.
4. `fillna(0.0)` is applied broadly to descriptor columns. Migration should distinguish true zero from missing/unknown measurements.
5. Model metadata should include dataset hash, feature schema, code commit, split protocol, MAE/RMSE/R² and model hash.

## formolecular/g_oraculo_aeroespacial.py

Observed migration issues:

1. The target is `AERO_Impulso_Espec_Teorico`, learned from molecular fingerprints alone.
2. Specific impulse is treated as if it were an intrinsic molecular property. Research OS moves this to the chain `FuelLab -> CombustionLab -> PropulsionLab` with chamber/oxidizer/nozzle conditions.
3. R² is displayed as a percentage of thermodynamic prediction accuracy. Research OS does not interpret R² that way.
4. The comment says the sample contains the “150,000 most varied molecules”, but the implementation uses random `df.sample(...)`.
5. The historical Isp target is classified as `HEURISTIC_REVIEW` until its label generation and independent physical/experimental provenance are established.
6. Growing the dataset by 50% currently increments `n_estimators` by 50. Research OS will replace this with candidate-vs-champion retraining and validation gates.

## Biolab/fabrica_g2.py

Observed migration issues:

1. Vina and OpenBabel paths/configuration are embedded in the script, including a Windows-specific OpenBabel path.
2. Vina/OpenBabel subprocess calls use shell command strings. New DockingLab uses explicit argument vectors and executable configuration.
3. A single global grid is reused for different receptor targets; the Research OS docking request keeps grid configuration attributable per run/target.
4. The RandomForest model is fitted and scored on the same X/y dataset. This training score is not an out-of-sample validation metric.
5. Multiple responsibilities are coupled in one script: receptor download/preparation, ligand preparation, docking, statistics, ML, report generation and filesystem cleanup. These are migration candidates for independent protocols/tasks.

## Migration decisions encoded in v1.3

- deterministic molecular targets -> direct calculator path;
- empirical targets -> ML candidate only after provenance/split audit;
- historical derived aero/efficiency targets -> quarantine/rederive;
- missing physical engine/evidence -> `INDETERMINATE` or `INSUFFICIENT_EVIDENCE`, never guessed PASS;
- legacy scripts remain untouched until replacement protocols are validated side-by-side.
