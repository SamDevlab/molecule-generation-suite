# APODOCK-001 v1.0.2 frozen input bundle

This bundle is the explicit remediation authorized by the provenance audit in [`apodock001-sdf-provenance-audit-v1.0.1.md`](apodock001-sdf-provenance-audit-v1.0.1.md). It does not overwrite v1.0 or v1.0.1 and does not change the cohort, chemistry policy, preparation contract, boxes, Vina identity, seed, CPU, exhaustiveness, num_modes, scoring, or analysis.

Protocol:

- ID: `research-os.apodock001.protocol.v1.0.2+aa40517362e14795`
- Hash: `aa40517362e14795a9ea4747b632fab81b2fc1f5bb49e4c880d9ad38699de03c`
- Bundle: `research-os.apodock001.input-bundle.v1+4be4265fa5917645`
- Bundle SHA-256: `4be4265fa591764512825f720f101b8d9b13def2edf520026347b55050f36468`
- Planned run ID: `research-os.apodock001.planned-run.v1+ff217589e517ab64`

The bundle manifest is [`inputs/apodock001/v1.0.2/manifest.json`](../inputs/apodock001/v1.0.2/manifest.json). It contains 34 immutable files:

- nine selected current RCSB instance SDFs for APD-001..APD-009;
- all 20 apo/holo PDBs for APD-001..APD-010;
- BEM/MAV ideal SDF and CIF source files;
- the APD-010 chemistry-gate report.

The bundle hash is derived from the deterministic manifest payload containing logical names, source provenance, case/role, byte SHA-256, and scientific identities. It excludes absolute paths, timestamps, machine metadata, and JSON formatting/order. The adapter verifies every byte locally before building the execution plan; no RCSB request is made during v1.0.2 preflight or planning.

The offline validation command is:

```text
python scripts/preflight_apodock001_v102_offline.py
```

It verifies the bundle, parses the nine SDFs, checks the APD-010 10/10 chemistry gate, builds the deterministic plan, verifies synthetic prepared-artifact staging, and emits a `NOT_EXECUTED` evidence scaffold. It does not import or invoke Vina.

The scientific diff against v1.0.1 is limited to the explicitly versioned input materialization and the derived protocol/bundle identities. v1.0.1 remains preserved with its original frozen hashes and `FROZEN_BUT_UNEXECUTABLE` audit status.

No APODOCK case was executed. No Vina docking command was started. No prospective pose or score was observed. The next authorization remains a separate, single prospective APODOCK-001 v1.0.2 run.
