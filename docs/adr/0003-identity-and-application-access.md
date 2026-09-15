# ADR 0003 — Verified identity and application access

Date: 2026-09-14

## Status

Accepted

## Decision

The authenticated Person is identified only by the verified OIDC issuer and
subject. Authentik is used through Passport/openid-client and the backend keeps
the resulting identity in a Valkey-backed server-side session. Username, email,
display name, and avatar are presentation data and never link accounts.

The selected Athlete is a separate storage partition. Every operation has an
explicit application permission map and unknown operations fail closed. The
Profile service evaluates grants at the HTTP and MCP boundaries: an Athlete
has full access, a Coach has broad training access, and a Handler has
competition-day access plus the documented reads. Grant administration belongs
to the Athlete. Cached report reads require read permission; report generation
requires write permission.

## Consequences

Existing Authentik subject mappings, including the operator, are preserved.
Legacy accounts need an explicit verified subject link; a shared display name
or email address cannot establish it. Ambiguous links fail closed.

The public OIDC issuer remains the authority even when server-side discovery,
token exchange and key retrieval travel through the internal Authentik Service.
Short-lived signed operation principals bind the acting Person, selected
Athlete and operation at HTTP/MCP boundaries. The internal API token alone is
insufficient to impersonate a Person.
