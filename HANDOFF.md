# Service rewrites in progress

All four service rewrites are implemented, and the legacy Python services have
been deleted. Go lift-profiles is deployed and healthy. Go export is deployed;
a spreadsheet formatting fix is awaiting CI verification. Do not treat the
latest deployment as final until that pipeline completes successfully.

The Go templates and Rust imports cutovers are prepared and being committed
together. Local cross-service tests pass. Their deployment and live verification
are pending.

A pre-existing race remains when sessions are copied while concurrent edits
occur. The work here does not include broad video changes or a rollout protocol
for that race; account for it separately before relying on copied sessions under
concurrent writes.
