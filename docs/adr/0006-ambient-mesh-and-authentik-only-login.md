# ADR 0006 — Ambient mesh and Authentik-only login

Date: 2026-11-11.

## Status

Accepted.

Supersedes the browser-login and service-authentication portions of ADRs 0002
and 0003. Their Person/Athlete separation, grants, publication rules and verified
subject linking still apply. ADR 0004 media delivery is unchanged.

## Decision

Authentik is the only application identity authority. Discord is an Authentik
source. OAuth2 Proxy owns browser redirects and its Valkey-backed session.
Express validates the proxy-forwarded OIDC token through the security service;
it has no Passport session or direct Discord OAuth callback.

Istio Ambient gives each portal workload an identity derived from its dedicated
Kubernetes ServiceAccount. Application HTTP and MCP operations pass through a
shared waypoint. Protected destination workloads accept only the waypoint, with
strict mTLS. The browser backend accepts only OAuth2 Proxy over mesh mTLS.

The waypoint calls `pl-security` through Envoy's external authorization API.
The shared waypoint uses one extension provider. The authorizer overwrites an
authorized-destination header on each allowed request. A separate Service-scoped
ALLOW policy requires that decision to match the actual destination. An untrusted
Host header or the waypoint's own identity cannot establish that binding.

The authorizer validates the source workload, operation principal and bounded
request body, then uses the existing Profile/PyCasbin modules and current stores.
HTTP and MCP share permission semantics. Unknown operations, malformed bodies,
unavailable policy data and invalid credentials deny access. Allow decisions are
not cached.

Only `pl-security` signs operation principals. Their five-minute lifetime and
Person, Athlete, operation, caller and destination bindings limit delegation.
Coach uses a separate finite, job-bound capability for work that outlives one
operation principal. Every resulting protected request still evaluates current
grants. Machine operations have explicit workload permissions.

Domain handlers retain input validation, ownership checks, publication filtering,
execution ownership and concurrency control. Analytics' Node helper remains
loopback-only, with its own intra-pod credential; mesh identity cannot distinguish
containers sharing a pod.

Verified Authentik Discord subjects may acquire conditional identity pointers to
the same Person. Email addresses and display names cannot establish links.
Conflicting links fail closed. Person keys and Athlete storage partitions do not
change.

## Consequences

OAuth2 Proxy, the waypoint and central authorization are required dependencies.
There are no runtime legacy modes or authentication fallback paths. The existing
single-node cluster does not gain availability from the mesh.
