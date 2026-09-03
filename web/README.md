# Chat-first interface boundary

The supported application boundary is `research_os.service`. A future web
client should call `OracleService.ask()` and the read methods for plan,
results, evidence, sources, history, runs and lineage. It must not import
`research_os.*.lab` modules directly.

The service returns a compact summary for normal users and retains plan,
engine manifests, hashes, bundles and lineage for technical inspection.

