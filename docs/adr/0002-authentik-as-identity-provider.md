# ADR 0002 — Authentik identity and application permissions

Date: 2026-07-02. Clarified: 2026-09-14.

## Status

Accepted. Authentik and the application-permission evaluator are deployed.
Per-operation acceptance evidence belongs in POWERLIFTING_FEATURES_BACKLOG.md.

## Decision

Keep Authentik as the identity provider. The gateway uses Passport and
openid-client to validate OIDC login and retains the verified issuer and subject
in server-side sessions in the existing Valkey. Provider subjects identify
Persons; display names and email addresses never link accounts.

Authentik's internal RBAC governs its own administration and authentication
flows. It does not implement the portal's Athlete grants. The Profile service
uses one PyCasbin evaluator for application permissions, loading current grants
and publication settings from the existing stores. The gateway and every typed
HTTP/MCP operation consult this evaluator. A selected role does not confer access.

Only the Athlete administers their grants. Coach grants default to broad training
access; Handler grants default to competition-day writes and read-only training
context. Stored tied Competition Entry dates determine expiry seven days after
the latest date. Peer reads remain independent. Transactional relationship
updates enforce one active Coach and one active Handler per Athlete.

## Consequences

Identity, selected Athlete and permissions are separate concepts. Revocation
and expiry affect the next operation, including reads of cached reports/media.
Coach/Handler note originals remain author-owned; shared attributed revisions
are attachments that the Athlete may remove but cannot rewrite.

This clarifies the original decision, which incorrectly assigned application
grants to Authentik's internal policy bindings. It also removes the proposed
unrelated database migration. Authentik keeps its existing supporting database;
Powerlifting data stays in its current DynamoDB/S3 stores.
