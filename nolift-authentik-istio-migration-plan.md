# NoLift Authentik and Istio migration

## 1. Summary and agreed decisions

Introduce Istio Ambient, centralize service authentication and permission evaluation,
and make Authentik the application's only login authority.

Decisions agreed with the operator:

- Cover the full original migration draft.
- Use an OIDC proxy to handle browser login and cookies.
- Retain Discord as an upstream Authentik identity source.
- Use a planned maintenance window for final cutover.
- Assign implementation to GPT-6 Luna and GPT-6.1 Terra using bounded tasks.
- This branch is mesh-only: remove legacy authentication and runtime fallback switches.
- Rollback means deploying the main branch; agents perform no Git operations.

Success means browser, Discord bot, HTTP, MCP, analytics, upload, and background
workflows continue through authenticated workload connections. Current Athlete
grants and publication rules remain effective.

### Verified starting point (2026-11-11)

One Ready K3s node runs Kubernetes v1.34.5+k3s1. Portal workloads are in
`powerlifting`; Authentik/Postgres are in `if-portals`. NGINX Gateway Fabric is
2.6.3 and Gateway API CRDs are v1.2.0. The current application hostname is
`dev.nolift.training`. Eighteen domain services mostly use the default
ServiceAccount. Express uses Passport, Valkey sessions, direct Discord login,
and Authentik OIDC. Shared internal tokens and principal-signing secrets are
present across gateway, services, and Coach. No Istio installation was found.

Preserve the configured application hostname and public Authentik issuer.
The original draft's example hostname does not authorize a hostname migration.

## 2. Target architecture and interfaces

### Browser authentication

```text
Browser -> Cloudflare Tunnel -> NGINX
                               |-- frontend
                               |-- /oauth2/* -> OAuth2 Proxy
                               |-- /api/* -> OAuth2 Proxy -> Express
                               `-- Authentik hostname -> Authentik -> Discord
```

OAuth2 Proxy takes over browser redirects and the login cookie. Istio policies
control workload access; they do not implement browser login.

- Reuse the existing Authentik OIDC provider and subject configuration.
- Register /oauth2/callback before retiring the Express callback.
- Reuse Valkey for proxy sessions with a separate key prefix.
- Use secure, HTTP-only, host-scoped cookies; PKCE and nonce validation.
- Keep the frontend and existing public reads available anonymously.
- Derive method-specific public exceptions from existing routes. Domain policy
  still decides which records are public.
- Return 401 JSON for unauthenticated protected API calls; the login button
  starts redirects.
- Forward the validated OIDC ID token internally. Strip incoming identity,
  principal, authorization-context, and internal-token headers first.
- Enforce same-origin checks on browser mutations.
- Preserve login-status responses; update login/logout for the proxy.

### Workload communication

```text
Caller -> source ztunnel -> destination waypoint -> destination ztunnel -> service
                                  |
                                  `-> ext_authz -> pl-security -> existing evaluator
```

Keep Kubernetes Service DNS, HTTP operation endpoints, MCP and existing payloads.
Give each portal workload a dedicated ServiceAccount. Use Ambient mTLS and one
shared portal waypoint initially. Enroll explicitly selected portal workloads;
keep Authentik, Postgres, monitoring, runner and unrelated workloads outside.
Use one gRPC external-authorization provider for the shared waypoint. Each allowed response overwrites an authorized-destination header; a Service-scoped ALLOW policy requires it to match the actual Service. Do not infer actual destination from a caller Host header or the waypoint identity. Attach HTTP policies with waypoint targetRefs and L4 policies to destination
workloads. Protected destination ports accept only the waypoint's identity;
enrollment labels alone do not prevent direct Pod-IP bypasses. Name HTTP Service
ports or set appProtocol. Preserve timeouts; add no automatic write retries.

Inventory gateway/domain/Coach/bot edges, analytics callbacks, Valkey and prompt
cache traffic. Permit only inventoried callers, destinations, ports and operations.

### Central security service

Add pl-security using the existing services image and shared Python evaluator:

- Envoy gRPC ext_authz Check API.
- Internal POST /v1/principals minting API.
- Internal access-evaluation API for gateway actions such as media access.
- Central private signing key and public verification keys.

Reuse current_context and check_context directly. Do not call protected Profile
HTTP routes from ext_authz and create an authorization cycle.

Choose body-aware authorization. Normalize /operations/{name} and MCP tools/call
using existing manifests and permissions. Bound inspected JSON to 10 MiB,
disable partial authorization, and return 413 for oversized requests. Reject
malformed envelopes, unknown operations, scope conflicts and unsupported MCP
methods. Permit initialization/discovery/valid notifications only for allowed
workloads. Recheck current grants on every protected operation; cache no allow
decisions. Never buffer upload bytes in ext_authz: preserve gateway upload bounds
and metadata/storage authorization.

Obtain workload identity from verified mesh attributes, never incoming headers.
Overwrite reserved access context with verified Person, Athlete and permissions.
Services populate existing _person_pk/_access from this trusted context. Retain
schema validation, ownership invariants, publication filtering, concurrency and
checks against local execution/job state.

### Principals and delegation

Use asymmetric principals through X-PL-Principal. Only pl-security holds the
private key. Bind Person, Athlete, operation, destination and permitted caller;
expire within five minutes. Browser identity starts from validated Authentik
claims. Anonymous contexts receive publication-based access only. Only the bot
workload can attest a Discord ID from its authenticated Discord connection; the
broker resolves an existing verified Person link. Never accept an arbitrary Person
in a mint request. Delegation preserves Person/Athlete and narrows to inventoried
edges. Durable Coach work retains initiating scope and rechecks access during
continuation and protected result reads. Keep job-specific Coach MCP capabilities.

Protect the mint API at the waypoint. Its Check call validates original caller
and delegation. Protect the separate gRPC Check port by workload policy without
recursively invoking ext_authz. Machine operations use explicit workload access,
without manufacturing human identities.

## 3. Infrastructure and identity migration

| State | Responsibility |
| --- | --- |
| core | Authentik and separated secrets |
| perms | Dedicated portal ServiceAccounts and required RBAC |
| network | Existing shared Gateway API CRDs, NGINX, routes, narrow ReferenceGrant, sanitation |
| new mesh | Istio base, istiod, CNI, ztunnel, extension providers |
| app | Proxy, pl-security, waypoint, app enrollment and policies |
| coach | Coach/bot identities, enrollment and destination policies |

Use a separate mesh S3 state key. Keep AWS resources in the AWS stack.
Initial pins: Istio 1.32.0 and OAuth2 Proxy 7.15.6. Validate NGINX/Gateway API
compatibility together before changing shared CRDs; record tested pins below.
Inspect actual host CNI paths before installation; global.platform=k3s is valid
only for the bundled CNI and matching paths. Keep the Authentik HTTPRoute in
powerlifting with a narrow ReferenceGrant in if-portals. Both routing resources
belong to the network state so its existing CRDs are installed first; retain
the CRDs in their existing state without moving ownership. Preserve listener scope.

CI order: core -> perms -> network -> mesh -> app -> Coach, with readiness gates.
Retain the existing in-cluster Coach apply and its separate state so a full
master pipeline run restores the complete deployment, as required by the operator.
Use one branch-derived tag for all six image builds and both image-consuming
Terraform stacks. Only master/main publish latest; no feature build updates it.
Agents perform no git writes, Terraform applies, AWS deletion or broad destructive
Kubernetes commands. Supply operator commands and reviewed artifacts instead.

Preserve Person keys, Athlete partitions, Authentik subjects, grants and note
ownership. Reuse identity_resolve verified linking. Provide an idempotent command
with dry-run and conditional writes. Link only verified provider IDs; report
ambiguities and never merge by email or names. Keep mappings additive. Verify
operator, Athlete, Coach, Handler and bot identities before disabling direct
Discord login. Add an ADR superseding transport/login portions of ADRs 0002/0003,
while retaining permission semantics and ADR 0004 CDN behavior.

## 4. Luna/Terra packets and quota controls

| Packet | Model / effort | Deliverable and gate |
| --- | --- | --- |
| 1 | Luna / low | Route/edge/port/secret inventory, fixtures, readiness and rollback digests; Terra validates boundaries |
| 2 | Terra / high | Principal, delegation, normalization contracts and negative tests |
| 3 | Terra / high | Mesh foundation and pilot enforcement before deploying the new branch |
| 4 | Luna / high | Identities, ports, enrollment, scoped secrets and CI wiring |
| 5 | Terra / high | Proxy, Express identity integration, frontend auth and tests |
| 6 | Terra / high | Body-aware ext_authz, trusted contexts, HTTP/MCP parity |
| 7 | Terra / high | Domain execution, Coach, bot, analytics and gateway caller migration |
| 8 | Terra / high | Dry-run/idempotent identity migration and tests |
| 9 | Luna / high | Acceptance checks; Terra security review |
| 10 | Terra / high | Operator cutover after live acceptance; rollback uses main branch |

Default one worker; at most two on disjoint work after interfaces are fixed.
Pass only packet context and relevant paths. Reuse workers for adjacent tasks.
Batch mechanical changes after one service passes. Escalate two failed Luna
attempts with evidence to Terra. Use no Max/Ultra and no duplicate full-repo
reviews. Record handoffs here. Run focused tests during implementation and the
required complete build before cutover and after cleanup.

## 5. Acceptance, cutover and rollback

Required checks:

- Authentik/Discord login preserves identities; expiry and logout work.
- Public reads work; private/unpublished data is denied.
- Forged headers/principals, expiry and mismatched scope fail.
- Unauthorized workloads fail via DNS, ClusterIP, Pod IP and alternate ports.
- Permitted workloads still need effective user permission.
- No direct access bypasses the waypoint; HTTP/MCP policy parity holds.
- Revocation, expiry, competition restrictions and cached reads remain correct.
- Adapter/policy failure denies; malformed/partial/oversized bodies fail safely.
- Largest existing imports fit the body bound.
- Coach nested tools, continuations, polling, cancellation and Discord preserve
  ownership. Analytics loopback remains loopback-only; mesh is not intra-pod auth.
- Uploads, media/CDN redirects, probes, metrics, caches and background work function.
- Relevant Python/Node tests, npm run typecheck and npm run build from src pass.
- Terraform validation/reviewed plans, Istio analysis and live negative tests pass.

Maintenance sequence: finish code/tests/images/plans/rollback preparation; capture
image digests and migration evidence; stop new portal writes/submissions and let
active work finish; install mesh and validate the pilot; deploy proxy,
security service, identities and policies; apply additive links; switch routing;
run browser/bot/bypass acceptance before reopening the portal. The new branch
contains no shared-token authentication, distributed signing keys, Passport
sessions or runtime fallback switches.

Observe adapter failures/latency, waypoint/proxy health and node resources using
existing monitoring. Never log tokens or request bodies. Rollback runs the full
master pipeline with apply_terraform=true and both partial-build flags false.
It rebuilds master images and restores its matching Terraform states, including
Coach. Preserve the original unused credential resources and CI secret inputs
for that reapply. Keep
additive links and installed infrastructure; do not uninstall CNI or shared CRDs
as incident recovery. Shared-node CNI changes and central authorization availability
are primary risks. A failed security gate keeps the portal in maintenance.

## Sources

- https://oauth2-proxy.github.io/oauth2-proxy/configuration/overview/
- https://istio.io/latest/docs/ambient/usage/waypoint/
- https://istio.io/latest/docs/reference/config/istio.mesh.v1alpha1/
- https://istio.io/latest/docs/ambient/install/platform-prerequisites/
- https://istio.io/latest/news/releases/1.32.x/announcing-1.32/
- https://github.com/oauth2-proxy/oauth2-proxy/releases/tag/v7.15.6
- https://learn.chatgpt.com/docs/models

## Implementation evidence and handoffs

- Plan saved on 2026-11-11. Live readiness rechecked; no warning events in
  powerlifting. Unrelated analytics migration leftovers predated implementation
  and were later explicitly authorized for deletion by the operator.
- Deployment requires a protected branch. This branch requires the completed mesh;
  no legacy/fallback mode is retained.
- Removed unused Rust analytics/rankings target directories and unrelated local
  dataset fixtures after checking that current code does not reference them.
- Server recovery preserved tracked edits but lost new helper/security files; the
  implementation workers were restarted and restored the required files.

- Integration review confirmed Istio permits one extension provider per waypoint.
  The implementation uses one provider with Service-scoped destination binding,
  rather than multiple providers. Direct Pod-IP access is denied by L4 policy;
  only protected Services enroll in the waypoint.

- Completed the mesh-only gateway, domain, Coach and bot caller migration; removed
  Passport, direct Discord application callbacks, shared HMAC signing and runtime
  compatibility switches. OAuth2 Proxy handles browser login, refresh and logout.
- Terra: full Python suite passes (377 tests, 15 subtests). Luna: root, core,
  perms, network, mesh, app and Coach Terraform scopes validate; changed HCL format
  checks and workflow YAML parsing pass. The pinned Istio chart templates and
  representative policies pass istioctl validation; NGINX 2.6.3 also renders.
- Gateway/frontend verification: 39 backend and 22 frontend Node tests pass;
  npm run build and npm run typecheck pass from src. Credential log redaction,
  malformed broker responses, origin checks and forged identity headers are tested.
- Gateway API CRDs retain their existing network-state ownership. The controller
  watches only powerlifting and the Authentik namespace for backend resolution;
  same-namespace route attachment remains enforced.
- Deployment provisions signing parameters through the separate security stack
  and runs the identity-pointer preflight and conditional migration automatically.
  Live bypass acceptance and rollback verification remain outstanding.
- Corrected the deployment contract after operator review: Packer publishes
  only the selected tag; app and Coach resolve the same branch-derived tag.
  Restored the existing Coach CI apply and dormant core credential resources
  needed by master's full pipeline reapply. The separate Istio foundation and
  additive identity links remain after application rollback.
