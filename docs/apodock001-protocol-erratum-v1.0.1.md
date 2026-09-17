# APODOCK-001 protocol erratum v1.0.1

Status: **FROZEN**. This erratum supersedes v1.0 for future prospective
execution, while preserving the original v1.0 manifest and audit trail.

## Root cause and boundary

The v1.0 manifest recorded this Vina digest:

```text
f31f774f723bba7bbbe6e9d1c47577020eea9a8da16424284c043d22593570644
```

It contains 65 hexadecimal characters and cannot be a SHA-256 digest. The
official Linux x86_64 Vina 1.2.7 asset has this 64-character digest:

```text
f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644
```

No receptor or ligand was supplied to Vina, no docking process was started,
and no score, pose, or raw docking output exists. The v1.0 manifest remains
unchanged and is classified as `FROZEN_BUT_UNEXECUTABLE`.

## v1.0.1 identity

The active manifest is
[`configs/apodock001-protocol-freeze-v1.0.1.json`](../configs/apodock001-protocol-freeze-v1.0.1.json).
Its only scientific correction is the Vina binary digest. The version and
derived identities are recomputed from the canonical scientific payload:

- protocol version: `1.0.1`
- protocol hash: `9e293289c972960333cdd442324c0c6c2485d0b3e90471f9882abfa3312a8f13`
- protocol ID: `research-os.apodock001.protocol.v1.0.1+9e293289c9729603`
- Vina: `1.2.7`
- Vina SHA-256: `f31f774f723bba7bbe6e9d1c47577020eea9a8da16424284c043d22593570644`

APD-001 through APD-010, chemistry `10/10`, the APD-010 BEM+MAV adapter
`1.0.0`, receptor and ligand preparation, boxes, seed `42`, CPU `1`,
exhaustiveness `16`, `num_modes` `20`, scoring, and analysis plan are
unchanged. The frozen Open Babel requirement remains `openbabel-wheel>=3.1.1.23`
and the normative version remains 3.1.1.

## Validation policy

Every declared SHA-256 or hash/identity field must be exactly 64 lowercase
hexadecimal characters. Uppercase hexadecimal is rejected by policy. Invalid
length, non-hexadecimal, uppercase, divergent input, chemistry, box, tool,
parameter, or derived identity values fail closed. Operational metadata such
as timestamps, absolute paths, JSON formatting, and irrelevant object order
does not enter the protocol hash.

The erratum is a protocol-only change. The execution adapter remains a
separate review and merge step and must consume v1.0.1 only after this
erratum is merged. CI may download the official binary, verify its digest,
and run `vina --version` only after the digest check; it must never pass
`--receptor` or `--ligand` in this validation.

The next authorized action is a separately reviewed prospective run branch:
`APODOCK-001 prospective execution using the frozen v1.0.1 protocol`.
