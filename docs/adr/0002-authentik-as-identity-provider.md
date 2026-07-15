# ADR 0002 — authentik as the identity provider and RBAC store

Date: 2026-07-02

## Status

Accepted (decision made; not yet implemented — Epic 4 is future work, only
Epic 1 is done)

## Context

Epic 4 (FEAT-4.1, FEAT-4.2) requires a battle-tested identity provider deployed
in the cluster that handles Discord social login, user attributes, sessions, and
credential rotation, plus granular RBAC for the Athlete / Coach / Handler
grant model (see `CONTEXT.md` People & Roles).

The backlog documented three options:

- **(A) Keycloak** — self-hosted, battle-tested, full RBAC, Discord as a social
  IdP via broker. Heavy: ~600MB JVM on a single-node cluster.
- **(B) Ory Kratos + Keto + Oathkeeper** — identity (Kratos), permissions (Keto,
  Zanzibar-style tuple relations), gateway (Oathkeeper). Lighter (~150MB each)
  but split across three services.
- **(C) AWS Cognito + Verified Permissions** — managed, zero cluster RAM.
  AWS per-active-user billing.

The operator's documented constraints: "battle-tested tools and libs," "add it
into the cluster" (favors self-hosted over managed), "passportjs similar"
(Passport.js is fine as the Node-side strategy).

## Decision

Use **authentik** as the identity provider and RBAC store.

authentik is a self-hosted, Python-based IdP that supports Discord as a social
identity provider, ships its own RBAC (policies, bindings, flows), and is
lighter than Keycloak on RAM (no JVM). The Coach and Handler grant-types will
be implemented as authentik policies/bindings — one service for both identity
and RBAC, not a separate permission store.

Deploy **Postgres** alongside authentik (via a cloud-agnostic Helm chart) in the
same effort. Postgres is not used yet — the DynamoDB → Postgres migration (see
ADR 0001 rationale) is not started — but having the database deployed and
visible keeps the planned migration in focus.

## Consequences

- One Python container for IdP + RBAC, fitting the cluster's resource budget
  better than Keycloak's JVM.
- No AWS per-active-user billing (unlike Cognito).
- Simpler to operate than the Ory trio (one service vs three).
- Coach/Handler grants are authentik policies, not a separate permission store.
  The grant model (tied to competitions, expiry at `max(tied comp dates) + 7d`,
  at most one active Coach and one active Handler per Athlete) is enforced via
  authentik policy bindings.
- Postgres is deployed but unused; it is a deliberate visual reminder for the
  future migration, not a production data store. The migration itself remains
  future work with no committed timeline.
- Existing Discord OAuth flow is replaced, not duplicated. Current operator /
  Discord users must be migrated to authentik when Epic 4 is implemented.

## Alternatives considered

- **(A) Keycloak** — rejected: JVM footprint (~600MB) is too heavy for a
  single-node bare-metal k3s cluster.
- **(B) Ory Kratos + Keto + Oathkeeper** — rejected: three services to deploy
  and operate where one (authentik) covers both identity and RBAC.
- **(C) AWS Cognito + Verified Permissions** — rejected: AWS per-active-user
  billing, and the operator prefers in-cluster self-hosted resources.
