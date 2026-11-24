# Service rewrites in progress

The Go lift-profiles service replaces the Python implementation and is deployed
with a healthy pod. Its focused tests and deployment pipeline passed.

The Go export rewrite and Python removal are implemented and committed and
pushed. Fixture parity and focused Go tests pass. Live deployment verification
is pending; do not describe the export cutover as deployed yet.

Rust imports and Go templates remain incomplete, and their Python
implementations remain active. Imports still needs a secured Program operation
that validates the import claim and performs guarded, idempotent publication.
Templates still needs append and replace-incomplete publication paths and full
compatibility checks. Shared Session guard changes are uncommitted and are not
safe to deploy: publication does not check the revision captured before reading
sessions, bulk writes can span transactions and be observed partway through, and
delayed thumbnail updates can update only an older program version.

The latest completed deployment pipeline succeeded and the service pods were
healthy. Export deployment verification will follow the pending push and its CI
deployment.
