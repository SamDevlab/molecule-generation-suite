# MOLDISC-016 — JE2 Source-Directed Robustness Megacampaign

MOLDISC-016 is a static, predeclared E2 computational campaign for the frozen
ATX-007 / 1KZK / JE2 non-cognate holo-crossdocking target. It preserves the
four-cell `A0B0/A1B0/A0B1/A1B1` panel and runs exactly eight planned docking
runs per docking campaign: baseline, Vina-seed sensitivity, starting-conformer
sensitivity, and exhaustiveness sensitivity. The complete plan contains 32
docking runs and permits no retries.

The protocol is pinned to Vina 1.2.7, one CPU, `num_modes=20`, Vina seeds
`42/1337/2025`, ETKDGv3 seeds `42/1337/2025`, exhaustiveness `8/16/32`, and
Open Babel Gasteiger preparation. A single target snapshot and receptor-frame
grid are shared by every run. The MOLDISC-012 control replay is fail-closed
against its frozen pose scores, scientific identities, and parent hash.

Baseline RUN_A is used for common-core geometry and 4.0 Å heavy-atom residue
contacts. Geometry is measured directly in the receptor frame without rigid
body alignment, centering, or a threshold. Factorial effects are descriptive
only; no p-values, significance testing, universal score, winner, or lead are
created.

The MOLDISC-015 C-2545 `-3.62` measurement remains source context and is not
transferred to any candidate. The evidence ceiling is `E2_COMPUTATIONAL`, with
experimental binding, exact C-2545 stereochemistry, single-structure, and
non-cognate-capability gaps retained explicitly. The first result is preserved
by the result manifest and its campaign hashes after execution.

The canonical frozen configuration is
`programs/moldisc-016-je2-source-megacampaign/program.json`; the runner is
`scripts/run_moldisc_016.py`. MOLDISC-017 is intentionally not opened by this
program.
