# ADR 0006 — Ambient mesh and Authentik-only login

Date: 2026-11-11. Revised 2026-11-12.

## Status

Accepted.

Supersedes the browser-login and service-authentication portions of ADRs 0002
and 0003. Their Person/Athlete separation, grants, publication rules and verified
subject linking still apply. ADR 0004 media delivery is unchanged.

## Decision

Authentik is the only application identity authority. Discord is an Authentik
source. OAuth2 Proxy owns browser redirects, token validation and its
Valkey-backed session. Express has no Passport session or direct Discord OAuth
callback. It reads the authenticated user from the headers OAuth2 Proxy sets.

Istio Ambient gives each portal workload an identity derived from its dedicated
Kubernetes ServiceAccount, with strict mTLS. The browser backend accepts only
OAuth2 Proxy. Workload-to-workload AuthorizationPolicies decide which workloads
may call which services.

The backend and the Discord bot state the acting Person in a request header when
calling domain services. Any workload that a policy allows to reach a domain
service is trusted to state the Person, and it forwards that Person on the
calls it makes. The Discord bot resolves the Person from the verified Discord
subject.

Each domain service authorizes per-user operations in-process with the existing
Profile/PyCasbin modules and current stores. HTTP and MCP share permission
semantics. Unknown operations, malformed bodies, unavailable policy data and a
missing Person on per-user operations deny access. Allow decisions are not
cached.

Starting a long-running job, such as an import or Coach generation, is a
per-user operation and is authorized as one. The job records the Person who
started it. After that, the job runs as its own workload.

Domain handlers retain input validation, ownership checks, publication filtering,
execution ownership and concurrency control. Analytics' Node helper remains
loopback-only, with its own intra-pod credential; mesh identity cannot distinguish
containers sharing a pod.

Verified Authentik Discord subjects may acquire conditional identity pointers to
the same Person. Email addresses and display names cannot establish links.
Conflicting links fail closed. Person keys and Athlete storage partitions do not
change.

There is no central authorization service, no signed per-operation principal and
no waypoint external authorizer.

## Consequences

OAuth2 Proxy and the mesh policies are required dependencies. There are no
runtime legacy modes or authentication fallback paths. A compromised workload
that is allowed to reach a domain service can act as any Person. The backend
and bot already see every user's identity, so they are trusted regardless. The
existing single-node cluster does not gain availability from the mesh.
