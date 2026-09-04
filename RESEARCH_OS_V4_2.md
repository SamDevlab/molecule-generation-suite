# Research OS v4.2 — User Corpus & Private Knowledge

Status: `INFRASTRUCTURE_READY_AWAITING_USER_CORPUS`

Branch: `research-os-v1.3`

The v4.2 private-corpus path is implemented and validated, but no user corpus
was present in the explicit local/project sources inspected for this milestone.
Repository documents remain project fixtures and were not relabeled as private
material.

The pipeline records a SHA-256 hash and metadata in `PrivateSourceRecord`,
creates `AUTO_EXTRACTED` candidates, and sends them to a review queue. It does
not persist private document text, execute extracted text, or automatically
promote anything to `VERIFIED`. Verification requires a source, locator,
readable supporting context, review action and clean extraction. Conflicting
private/public sources remain `REVIEW_REQUIRED` without an automatic source
preference.

No corpus-grounded ResearchPrograms were executed because none could be
grounded in a reviewed user corpus. The next corpus-dependent gate is therefore
honestly pending user material.

Readiness artifact: `.research-os-live-4.2/user-corpus-readiness.json`.
