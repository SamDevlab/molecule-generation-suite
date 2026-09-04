# Research OS v1.6 — Real Data Validation

Status: complete on `research-os-v1.3` at the milestone commit recorded in the release notes.

## Scope

v1.6 adds a real empirical molecular ML path without changing the v1.5 ledger, bundle, planner, or legacy lab contracts. The path is:

`External Source → SourceRecord → Raw Dataset → Validation → DatasetManifest → Curated Parquet → FeatureSchema → SplitManifest → TrainingRun → Candidate → Validation → Applicability Domain → Uncertainty → External Test → PromotionDecision → ModelArtifact → ResearchBundle → Ledger`.

The first target is aqueous solubility LogS from AqSolDB dataset G. This is an empirical target, not a deterministic molecular descriptor such as molecular weight, TPSA, QED, or ring count. The baseline uses Morgan radius-2 fingerprints and a NumPy ridge regressor. It reports MAE, RMSE, and R²; R² is a regression score and is never described as confidence or reliability.

## Source, license, and conditions

The implementation pins the official `dataset-G.csv` source to commit `8e02b548fd9a78778ff89a5aa9a460d1a289cc3a` and expected SHA-256 `e3b80a24edb5528fe3a7c4a808b26045804c73680183f43c21afbec905158071`. The source record retains the upstream CC0-1.0 data-directory license and its third-party-rights disclaimer. The checked-in fixture is a 46-row derived subset; the full 1,144-row source is downloaded only through the explicit pinned downloader.

AqSolDB standardizes the target as `LogS = log10(mol/L)`. Dataset G is the Delaney subset with experimental solubility values at approximately 25 °C. The manifest records target `Solubility`, units `log10(mol/L)`, aqueous medium, experimental measurement type, temperature 25 °C, source methods retained upstream, source URL, license, raw hash, and provenance. The upstream publication explains the curation, unit standardization, SMILES validation, and the physical-condition dependence of aqueous solubility: [official AqSolDB repository](https://github.com/mcsorkun/AqSolDB), [AqSolDB publication](https://www.nature.com/articles/s41597-019-0151-1), and [upstream data license](https://raw.githubusercontent.com/mcsorkun/AqSolDB/8e02b548fd9a78778ff89a5aa9a460d1a289cc3a/data/LICENSE).

## Split, model, AD, and uncertainty

Molecular data use scaffold split by default (`31/5/10` train/validation/test for the checked-in sample), with persisted record IDs and dataset hash in `SplitManifest`. The existing random, scaffold, cluster, source, group, temporal, and external-test splitters remain available. An external test is not invented from the same split: the v1.6 golden run records `external_test_acceptable=False` because it has no independent source.

Applicability domain is maximum Morgan/Tanimoto similarity to training fingerprints with threshold 0.4. `PredictionResult` contains prediction, uncertainty, OOD score, in-domain flag, model ID, dataset ID, feature schema ID, and run ID. `OUT_OF_DOMAIN` predictions are retained for audit and explicitly excluded from normal ranking.

Uncertainty is an absolute-residual 90th-quantile prediction interval calibrated on the validation split (training residual fallback only when validation is empty). The interval is an uncertainty artifact, not a certainty claim. Promotion evaluates metrics, candidate-versus-champion regression when a champion exists, external-test acceptability, applicability domain, calibration record, OOD score, and uncertainty thresholds.

## Golden run and honest outcome

`REAL-DATA-GOLDEN-RUN` enters the v1.5 ledger with:

- dataset `aqsoldb-g-real-sample@1.0.0`, 46 real curated experimental rows;
- model `MODEL-AQSOLDB-G-REAL-GOLDEN`, training run `TRN-AQSOLDB-G-REAL-GOLDEN`;
- real-data incumbent champion baseline `MODEL-AQSOLDB-G-REAL-SAMPLE-REAL-BASELINE` (training-target median), compared explicitly against the candidate;
- scaffold split `SPLIT-REAL-DATA-GOLDEN`;
- real model metrics MAE `1.8262661046818258`, RMSE `2.314557008775928`, R² `-0.25512633074854363` on the held-out test split;
- source, training/validation, AD/uncertainty, and promotion evidence;
- explicit promotion `REJECTED`, with FIRST_LOSS `ML-PROMO-EXT-001` because the held-out split is not an independent external test.

The run is sealed with FIRST_LOSS, its bundle verifies PASS, and the ledger indexes the dataset, candidate/champion models, their training-run references, four evidence records, claim, and FIRST_LOSS. The claim is `INSUFFICIENT_EVIDENCE` for deployment/generalization, reflecting the small derived sample, negative baseline R², lack of independent external test, and rejected promotion. This is a validation milestone, not a production model release.

## Non-goals and unchanged surfaces

No v1.7+ work is claimed. Knowledge OS, Oracle, Research Planner, Memory, chat interface, and automatic natural-language research execution remain v1.7+ scope; the v1.6 CLI exposes only `research-os run real-data-golden`. Existing legacy labs and `Biolab/`/`formolecular/` are untouched. The v1.5 synthetic ML golden fixture remains clearly marked synthetic and is not used as evidence for this real-data path.
