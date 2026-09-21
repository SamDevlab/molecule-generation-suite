# Legacy Model Audit Backlog

This v0.1 increment inventories model artifacts but does not deserialize or
execute them and does not perform a full audit of millions of historical rows.

Future review questions:

- What train/test split was used?
- Was the split random, scaffold-based, or otherwise grouped?
- Are duplicate structures or near-duplicates present across splits?
- Is there target leakage or a derived label leak?
- Are labels synthetic, heuristic, or externally measured?
- Is there an independent external validation set?
- Are units, conditions, and target definitions compatible with current claims?

Until answered, all metrics remain `SELF_REPORTED_PROJECT_METRIC`. QED should
prefer deterministic RDKit calculation when the exact property is available,
unless a surrogate has a justified operational purpose.
