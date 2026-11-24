# Service rewrites in progress

The Go lift-profiles service replaces the Python implementation and has focused
tests plus build and deployment definitions. Its Program update checks for
concurrent changes to lift profiles. Live deployment verification is pending.

The Rust imports service has a server, inference continuation, and a restricted
template handoff. Its session import needs a restricted Program operation that
is not yet implemented. Program pointer checks alone cannot protect an import
from concurrent Session edits: Session writers update their own records without
advancing the pointer. A safe commit needs a shared, atomically updated Session
revision or another guard respected by every writer, including during rollout.

The Go export and templates services remain incomplete. Templates supports
starting a new block, but still needs safe append and replace-incomplete paths
and full compatibility verification; export needs output parity verification.
Templates' index transaction requires a safe transition from both old writers,
templates and imports, which must not overlap with the new transactional writer.

Do not route traffic to the replacement services or remove their Python code
until their operation contracts, authorization, storage and rollout behavior
have been verified. Complete pipeline images, workload permissions and mesh
policies alongside each verified cutover.
