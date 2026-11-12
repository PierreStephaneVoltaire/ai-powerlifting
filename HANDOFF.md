# Handoff — 2026-11-12

## Live state (verified 2026-11-12)

- Site: https://dev.nolift.training (namespace `powerlifting`). Authentik runs in `if-portals`.
- Test login: user `test`, password `Demo-a40a214db8a0` (reset today with `ak shell` in the authentik-server pod).
  On the Authentik screen, use the username/password form, not "Continue with discord".
- Verified in a headless browser through the real login: OAuth2 Proxy → Authentik → app,
  `/api/auth/me` 200, the dashboard fully populated, the `/sessions` list, and the session
  detail for 2026-11-12. No API calls returned 4xx/5xx.
- All 17 `pl-*` services, oauth2-proxy, pl-security (2 replicas), backend and frontend are Running.

## Pending task: remove pl-security (ADR-0006)

### Deploy 1 — code done 2026-11-12, waiting on commit + pipeline

- Backend reads the Authentik ID token that OAuth2 Proxy passes in `Authorization`
  (`src/backend/src/auth/oidcIdentity.ts`), checks issuer/audience, then calls the
  `identity_resolve` operation on pl-profile. Discord alias linking moved into that handler
  (`handlers/user/identity_resolve/discord_links.py`).
- Backend, Coach, the Discord bot and domain services send `X-Person-Pk` / `X-Athlete-Pk`
  (`src/backend/src/utils/serviceHeaders.ts`). No principals, delegation or job capabilities.
- Domain services run `current_context` + `check_context` in-process
  (`services/app.py::authorization_context`). Internal-only operations require the caller to be
  the backend, read from the waypoint-stamped `x-pl-source-principal` header
  (`terraform/k8s/app/waypoint_identity.tf`, `services/mesh.py`).
- Coach authorizes jobs by calling pl-profile `access_context` with `operation` + `arguments`.
- Mesh: per-service ALLOW caller policies (`service_callers` in `terraform/k8s/app/mesh.tf` and
  `terraform/coach/mesh.tf`) replace the CUSTOM ext_authz and authorized-destination policies.
  pl-security Deployment/Service/secret are removed in the app stack.
- Packer init now authenticates with the workflow token (GitHub API rate limit flake).

### Deploy 1 — deployed and browser-verified 2026-11-12 (login, dashboard, sessions, analysis, profile)

### Deploy 2 — code done 2026-11-12, waiting on commit + pipeline

- `terraform/k8s/mesh/main.tf`: `nolift-security` extensionProvider removed.
- `terraform/k8s/perms/portal_accounts.tf`: `pl-security` ServiceAccount removed.
- CI `security-apply` job removed; `terraform/security` stays only so the operator can destroy it.
- Done live: hot-fix ConfigMaps deleted; 152 old `Media#` rows deleted from `if-health` after
  confirming each exists in `workout-Videos`.
- Operator, after deploy 2: `terraform -chdir=terraform/security destroy` (removes the two
  `/powerlifting/security/principal-signing-*` SSM parameters), then delete `terraform/security`.

Keep them separate: the mesh stack applies before the app stack, so removing the provider in
deploy 1 would deny all traffic until the CUSTOM policies are gone.
