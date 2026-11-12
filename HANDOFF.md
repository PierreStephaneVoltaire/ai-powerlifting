# Handoff — 2026-11-12

## Live state (verified 2026-11-12)

- Site: https://dev.nolift.training (namespace `powerlifting`). Authentik runs in `if-portals`.
- Test login: user `test`, password `Demo-a40a214db8a0` (reset today with `ak shell` in the authentik-server pod).
  On the Authentik screen, use the username/password form, not "Continue with discord".
- Verified in a headless browser through the real login: OAuth2 Proxy → Authentik → app,
  `/api/auth/me` 200, the dashboard fully populated, the `/sessions` list, and the session
  detail for 2026-11-12. No API calls returned 4xx/5xx.
- All 17 `pl-*` services, oauth2-proxy, pl-security (2 replicas), backend and frontend are Running.

## Pending task: remove pl-security (ADR-0006 was rewritten today)

`docs/adr/0006-ambient-mesh-and-authentik-only-login.md` now describes the target design. No code
has changed yet.

Target design:

1. OAuth2 Proxy validates login. Express reads the user from proxy headers: add
   `--set-xauthrequest` / `--pass-user-headers` to oauth2-proxy in
   `terraform/k8s/app/security.tf`. The backend accepts traffic only from the oauth2-proxy
   service account (`mesh.tf` `backend_from_oauth2_proxy`, which already exists).
2. The backend and the Discord bot send the acting Person in a header to domain services. The
   bot resolves the Discord subject to a Person through the identity pointers in DynamoDB.
3. Workload-to-workload Istio AuthorizationPolicies control who can call which service. The
   caller map already exists as `security_allowed_callers` in `terraform/k8s/app/security.tf`;
   turn it into per-service ALLOW policies.
4. Each domain service calls `check_context` (`src/services/authorization.py`) in-process for
   per-user operations. Starting a job is authorized as a per-user operation. The job then runs
   as the service, with the initiating Person stored on the job record.
5. Delete: `src/services/security/`, `src/services/principal.py`, `src/services/coach/principal.py`,
   `src/backend/src/auth/{security,principal}.ts`, the `/v1/identity` call in
   `src/backend/src/middleware/meshAuth.ts`, the pl-security Deployment/Service/ext_authz
   provider/destination-binding policies, and `terraform/k8s/mesh/main.tf` extensionProviders.

Files that reference principals or pl-security and need edits:

- Python: `src/services/{app,execution,generations,authorization}.py`,
  `src/services/coach/{model,services}.py`, `src/services/coach_discord/coach_client.py`,
  `src/services/handlers/analysis_reports/composite.py`
- Backend: `src/backend/src/{analyticsSidecar.ts,utils/logger.ts,middleware/meshAuth.ts}`
- Terraform: `terraform/k8s/app/{portal,mesh,services,analytics,security}.tf`,
  `terraform/k8s/{mesh/main.tf,network/routes.tf,perms/portal_accounts.tf}`,
  `terraform/coach/{agent,discord}.tf`

Order: cut over consumers first (backend, services, coach, bot) while pl-security is still up,
deploy, then delete pl-security and the ext_authz provider in a second deploy.
