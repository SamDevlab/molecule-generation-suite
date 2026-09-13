# APODOCK-001 v1.0.2 diagnostic matrix

This matrix is derived only from the sealed historical run. It does not rewrite the historical analysis and does not invoke Vina.

| Case | Execution | Runtime (s) | Box | Pose 1 RMSD | Best RMSD | Best pose | First loss |
|---|---:|---:|---|---:|---:|---:|---|
| APD-001 | COMPLETED | 91.576 | BOX_COVERAGE_OK | 5.606383981682715 | 3.3235114341480663 | 5 | — |
| APD-002 | COMPLETED | 347.836 | BOX_COVERAGE_OK | 7.231624554587633 | 4.762285299721937 | 15 | — |
| APD-003 | COMPLETED | 62.704 | BOX_COVERAGE_OK | 6.858354838333819 | 4.3644501338240795 | 12 | — |
| APD-004 | COMPLETED | 38.595 | BOX_COVERAGE_OK | 3.6525388501748277 | 2.6464435368886092 | 18 | — |
| APD-005 | COMPLETED | 58.023 | BOX_COVERAGE_OK | 3.1640655087825422 | 2.556364201549729 | 5 | — |
| APD-006 | FAILED | 901.483 | BOX_COVERAGE_OK | — | — | — | EXECUTION_FAILED |
| APD-007 | COMPLETED | 110.952 | BOX_COVERAGE_OK | — | — | — | POSE_CONVERSION_FAILED |
| APD-008 | COMPLETED | 835.891 | BOX_COVERAGE_OK | 6.384141352703716 | 4.894071813461033 | 15 | — |
| APD-009 | COMPLETED | 74.152 | BOX_COVERAGE_OK | 3.323365930623804 | 2.349907497850655 | 10 | — |
| APD-010 | COMPLETED | 872.547 | BOX_COVERAGE_OK | — | — | — | REFERENCE_COORDINATES_INCOMPLETE |

Interpretation: every mapped reference remained inside its frozen box, while every determinate case remained above 2 Å even after considering up to 20 returned poses. The score/RMSD correlations and pairwise pose spreads are descriptive diagnostics only; they do not establish causality.

The v1.0.2 historical result remains unchanged.
