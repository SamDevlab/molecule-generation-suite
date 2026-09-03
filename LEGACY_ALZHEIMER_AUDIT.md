# Legacy Alzheimer-related audit

The repository contains enough explicit references to document a legacy
Alzheimer-related computational thread, but not enough to claim biological or
clinical validity.

| Field | Repository evidence | Research OS interpretation |
|---|---|---|
| target | `4EY7`, described in `formolecular/novo_horizonte/a.py` as a human crystal and used as an AChE efficacy column | source/protein identity must be externally verified before scientific claims |
| protein | AChE wording appears in legacy plotting/comments; `5W8K` is labelled hERG in `formolecular/test.py` | target and off-target roles must be explicit in a new config |
| species | `4EY7` is textually called human; other legacy structures do not carry a complete species manifest | use `HUMAN` only for the explicit 4EY7 comment; otherwise `UNKNOWN` |
| receptor | legacy PDB/PDBQT files and `receptor_4EY7.pdbqt`/`receptor_5W8K.pdbqt` are present | receptor provenance, preparation and hash must be recorded |
| model | legacy files include serialized XGBoost models and generated candidates | ML model provenance and OOD status are unverified |
| dataset | `banco_mestre_humano.csv`, `banco_mestre_unificado.csv`, and generated rankings exist | source, license, split and synthetic feedback are unverified; quarantine applies |
| docking protocol | Vina/Open Babel subprocess calls and a 4EY7 grid appear in legacy scripts | this is at most a historical computational trace; it is not a validated reference protocol |
| evidence | CSV scores, poses and plots are stored; no independent experimental validation was found by this audit | computational evidence ceiling remains E2; no cure/efficacy claim is supported |

This audit records what is present and what is missing. It does not recreate,
execute or endorse the legacy workflow.

