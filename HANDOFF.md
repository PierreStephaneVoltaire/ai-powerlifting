# Service rewrites in progress

The Go lift-profiles service replaces the Python implementation and is deployed
with a healthy pod. Its focused tests and deployment pipeline passed.

The Go export, Rust imports, and Go templates services are still incomplete.
Their Python implementations remain active; none of these replacements has
been routed into production. Export, imports, and template parity fixes are
committed and pushed, with new CI checks pending. Shared Session guard changes
remain uncommitted.

Export now restores workbook analysis, correlation findings, and program
evaluation sections, but still needs full output, authorization, and integration
parity checks. Imports has 20 passing Rust tests, including fixes for rejecting
only imports awaiting review and matching notes to numeric training days. It
still needs a secured Program operation that validates the import claim and
performs guarded, idempotent publication. The Go templates service has focused
parity fixes, but append and replace-incomplete publication paths and full
compatibility checks remain unfinished.

The shared Session guard is not safe to deploy yet. Publication does not check
the revision captured before reading sessions, bulk writes can span transactions
and be observed partway through, and delayed thumbnail updates can update only
an older program version. Do not deploy these guard changes or cut over imports
and templates until a coordinated concurrency and rollout protocol is complete.

The latest completed deployment pipeline succeeded and the service pods were
healthy. CI checks for the latest pushed commit are pending.
