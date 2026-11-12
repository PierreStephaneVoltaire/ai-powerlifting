# Move Authentik and its Postgres into the powerlifting namespace

## Live state (2026-11-12)

- `if-portals` runs `authentik-server`, `authentik-worker` (chart 2026.5.3) and the CNPG
  cluster `postgres` (2 instances, 10Gi `postgres-local-path` each, database `authentik`, 163 MB).
- Terraform for all of it lives in `terraform/k8s/core` (moved there on 2026-11-06 by
  state rm + import), placed by `auth_namespace = "if-portals"` from the `K8S_TFVARS` secret.
- Consumers of that location: the `authentik` HTTPRoute plus a ReferenceGrant in `if-portals`
  (network), the `authentik-powerlifting-oidc` secret read by oauth2-proxy (core → app), the
  backend `AUTHENTIK_JWKS_URL` (core), and the Authentik Terraform provider (core).
- The state's `random_password.postgres` and `random_password.authentik_secret_key` equal the
  live secrets, so the new deployment reuses both: the same secret key keeps signed tokens and
  sessions valid, and the copied database keeps users, Discord links, refresh tokens and config.
- Pods join the mesh only with `istio.io/dataplane-mode=ambient`; the new pods do not carry it,
  matching today.

## Deploy 1 (one push, pipeline only)

core:
- `authentik_postgres`: secret `authentik-postgres-app` (same password) and a CNPG cluster
  `authentik-postgres` in `var.namespace`, bootstrapped with `initdb.import` (microservice,
  database `authentik`) from an external cluster at `postgres-rw.<auth_namespace>`.
  The apply waits until the cluster is healthy.
- `authentik_env`, `authentik_token`, the Helm release and the bootstrap job are added again in
  `var.namespace`, pointing at `authentik-postgres-rw`. The old copies in `if-portals` stay
  untouched and keep serving until the route moves.
- `authentik-powerlifting-oidc` moves to `var.namespace`; `AUTHENTIK_JWKS_URL` points at the
  new service.

network: the `authentik` route targets `authentik-server` in `var.namespace`; the ReferenceGrant
in `if-portals` is removed.

app: oauth2-proxy reads `authentik-powerlifting-oidc` from `var.namespace`.

Writes made to the old database between the import and the route switch (a few minutes) are not
copied; at worst a login made in that window has to be repeated.

Verify after the pipeline: new pods healthy, `auth.nolift.training` served by the new pods,
password login as `test`, an existing session refreshing, dashboard and sessions loading, and
old/new user counts equal.

## Deploy 2 (after verification)

- The Authentik provider reads the service from `var.namespace`.
- Operator removes the old resources from core state without destroying them:
  `terraform -chdir=terraform/k8s/core state rm kubernetes_namespace_v1.auth kubectl_manifest.postgres helm_release.authentik kubernetes_secret_v1.postgres kubernetes_secret_v1.authentik_env kubernetes_secret_v1.authentik_token kubernetes_job_v1.authentik_bootstrap_token`
  and the old blocks are deleted from code with the `auth_namespace` variable.
- Operator deletes the old workload when satisfied: `kubectl delete namespace if-portals`
  (this also removes the remaining IF objects there: openwebui and tinyauth routes, fission and
  nginx-gateway roles).
