# Model registry

`ModelRegistry` keeps model artifacts, stages, training references and
promotion gates separate from deterministic calculators and physics engines.
An ML model can produce E1 evidence only under its declared validation/OOD
contract; R² is never a confidence percentage.

