# S3 / Biolab compute contract

S3 is a future compute substrate, not a scientist, evidence authority, or
claim authority. MOLDISC-019 does not integrate S3 and its CI does not depend
on S3.

```text
Biolab
  ↓
Research OS frozen compute request
  ↓
S3 kernel execution
  ↓
result + implementation identity
  ↓
Research OS verification
  ↓
Evidence
```

## Integration gate

`S3_PRODUCTION_INTEGRATION_ALLOWED=false` until a functioning closed physical
feedback loop exists and a validated repeated computational kernel is shown,
with measured throughput/cost, to be a real bottleneck.

## Roadmap

- S3-0: language/runtime development.
- S3-1: scientific microkernels.
- S3-2: kernel equivalence against a trusted baseline.
- S3-3: Research OS execution adapter.
- S3-4: measured throughput/cost advantage.
- S3-5: Biolab high-throughput production use.

Future cost records may include compute wall time, CPU time, estimated compute
cost, measurable energy, external experiment cost, human intervention count,
hypothesis count, candidate count, and experiment count. Unavailable values
must remain unavailable rather than fabricated.
