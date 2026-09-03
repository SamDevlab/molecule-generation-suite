# Research OS v1.7 Engine Registry

The registry separates discovery from execution and reference validation. A
probe only imports a Python module or invokes an executable with a fixed argv
version command; it does not generate scientific results.

| Engine | Kind | Protocol boundary | Evidence ceiling |
|---|---|---|---|
| RDKit | deterministic library | molecular structure/property protocol | E2 computational |
| Cantera | physics engine | adiabatic equilibrium HP with recorded mechanism/phase | E3 physics simulation |
| Open Babel | preparation engine | explicit ligand/receptor conversion | E2 computational |
| AutoDock Vina | computational engine | target-specific grid, seed, receptor and ligand hashes | E2 computational |
| pymatgen | materials engine | composition feature schema with explicit fraction basis | E2 computational |
| matminer | materials engine | versioned composition descriptors/schema | E2 computational |
| pycalphad | physics engine | explicit TDB database and provenance | E3 physics simulation |

`AVAILABLE` means the implementation can be discovered. `CONFIGURED` means an
executable/database path is present. `PROTOCOL_READY` means the input contract
is satisfied. `REFERENCE_VALIDATED` is reserved for an executed, checked
reference case. A missing required engine or database is `INDETERMINATE`, never
a heuristic fallback or a successful result.

Vina and Open Babel are external executables and are intentionally not declared
as pip dependencies. Their adapters use argv execution with `shell=False` and
timeouts.
