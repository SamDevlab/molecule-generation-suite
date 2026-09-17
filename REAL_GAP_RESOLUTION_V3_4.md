# Real gap resolution — Research OS 3.4

The live record is
`.research-os-live-3.4-final3/real-resolution-acceptance.json`. Each attempt
has a unique digest and is also indexed in
`.research-os-live-3.4-final3/resolutions.sqlite`; previous campaign gaps were
not overwritten.

| Gap | Attempt | Result | New runs | Evidence boundary | Remaining gap |
| --- | --- | --- | --- | --- | --- |
| `GAP-EXTERNAL-AQSOLDB` | same AqSolDB-G lineage audit | `UNRESOLVED` | none | `E1_ML` | independent, overlap-audited and license-compatible solubility dataset |
| `GAP-COMB-VALIDATION` | H2 Cantera φ 0.8/1.0/1.2 | `PARTIALLY_RESOLVED` | 3 | `E3_PHYSICS` | matched experiment at E4 |
| `GAP-P-MAT-01-CONDITIONS` | source/condition matrix | `UNRESOLVED` | none | `E0_HEURISTIC` | source-located alloy observation with composition, processing, microstructure, environment, temperature, pressure, stress and method |
| `GAP-P-BATT-01-CONDITIONS` | NASA PCoE RW3 artifact retrieval and MATLAB parse | `PARTIALLY_RESOLVED` | 1 sealed run | `E4_CURATED_EXPERIMENTAL` | capacity/resistance/uncertainty needed for a complete degradation trajectory |
| `GAP-PHARMA-DOCKING` | Vina/Open Babel availability and preparation gate | `BLOCKED` | none | `E4_CURATED_EXPERIMENTAL` target identity only | configured executables, prepared artifacts and safe 1PXX reference docking |

## Battery artifact provenance

- Source: NASA Open Data, “Randomized Battery Usage 3: Room Temperature
  Variable Recharge Random Walk”.
- Landing page:
  <https://data.nasa.gov/dataset/randomized-battery-usage-3-room-temperature-variable-recharge-random-walk>
- Download resource:
  <https://data.nasa.gov/docs/legacy/ames/3.Battery_Uniform_Distribution_Variable_Charge_Room_Temp_DataSet_2Post.zip>
- License metadata: <https://www.usa.gov/government-works>
- Retrieved: `2026-09-03T22:08:44.199531-03:00`.
- Artifact SHA-256:
  `4e757b8b4e574202c32702000e1002f7a235d1c83a5729cef584ce528f3a4859`.
- Archive members: four MATLAB files (`RW1.mat`, `RW2.mat`, `RW7.mat`,
  `RW8.mat`), matching R data files, a README and an example plotting script.
  Only MATLAB data members and the README were read; scripts were not run.
- Parsed schema: `procedure`, `description`, `step`; each step contains
  `comment`, `type`, `time`, `relativeTime`, `voltage`, `current`,
  `temperature`, and `date`.

The measured summary is descriptive rather than a fitted degradation model.
The four cells contributed 17,065, 16,987, 17,277 and 16,302 steps. Operation
counts were respectively RW1 `D=6699/C=1281/R=9085`, RW2
`D=6576/C=1338/R=9073`, RW7 `D=6755/C=1313/R=9209` and RW8
`D=6268/C=1312/R=8722`. The adapter explicitly excludes RW2's out-of-range
temperature sentinel samples and reports that exclusion count.

## Scientific ceiling

The public NASA artifact supports a source-backed E4 description of recorded
measurements and their documented protocol. It does not, by itself, support a
condition-complete predictive degradation claim. Likewise, Cantera is used
only as the declared equilibrium physics engine; NIST WebBook is registered
as a `DATABASE`/reference source and is never called as an engine.
