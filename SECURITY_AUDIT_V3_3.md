# Security and scientific-boundary audit — Research OS 3.3

## Passed controls

- Live Codex transport remains local `codex exec`, read-only sandbox, no
  external LLM API and no shell execution from model output.
- Discovery output is allowlisted to registered problem/source IDs. Unknown
  IDs, source URLs and malformed 3-primary/2-secondary selections fail closed.
- Retrieved source summaries explicitly mark source content as DATA ONLY. They
  cannot add EvidenceLevel, claims, runs or engine results. Injection-shaped
  source content is covered by the campaign contract test.
- Campaign execution dispatches only known catalog problem IDs and registered
  Lab protocols. The manager never executes a source URL or free-form model
  text.
- Target records carry gene/protein, species, source and structure IDs;
  missing species becomes `UNKNOWN`, and the pharma campaign stops before
  docking when preparation/engine state is unavailable.
- Sealed runs and bundles are immutable; the Ledger verifies bundle integrity,
  lineage, claim/evidence references and engine provenance.
- OOD outputs are excluded from ranking and uncertainty is explicitly described
  as an interval estimate, not certainty.

## Deliberate limitations

- The legacy repository contains historical patterns outside this milestone;
  they are not imported into the campaign executor and remain covered by the
  prior legacy audit.
- A registered public citation is not automatically an experimental result.
  Source-synthesis campaigns therefore stop at `INSUFFICIENT_EVIDENCE`.
- Cantera is a bounded computational engine in this milestone. GRI30 output is
  not promoted to operational, hardware, safety or universal chemistry advice.
- The Codex test provider is deterministic and useful for integration only; it
  is never presented as live scientific discovery.
