# Kubernetes stacks

The `kubernetes-apply` job on the in-cluster Actions runner applies core, perms,
network, mesh and app. A successful Coach image build or a Kubernetes change
also selects the separate Coach state.

| Stack | Holds |
|---|---|
| `core` | Namespaces, config, application secrets, registry pull secret, Actions runner controller and scale set, Authentik and its CNPG Postgres cluster, NoLift identity objects in Authentik, monitoring |
| `perms` | Service accounts, roles and bindings (registry refresher, runner deployer bound to `cluster-admin`) |
| `network` | Gateway API CRDs, NGINX Gateway and data plane, app and Authentik routes, cloudflared, narrow Authentik `ReferenceGrant` |
| `mesh` | Pinned Istio Ambient base, control plane, CNI and ztunnel |
| `app` | `pl-*` services, analytics, Valkey, portal backend and frontend, registry token refresher |

The deploy job requires the repository owner as both actor and triggering actor.
Eligible pushes go to `master` or a branch with an open pull request. A manual
run selects deployment with `apply_terraform=true`.
It writes `K8S_TFVARS` (the full `k8s.tfvars`, see `k8s.tfvars.example`) to a
temporary file. It applies `core`, `perms`, `network`, `mesh`, then `app`.
Coach uses `COACH_TFVARS` and the state key `powerlifting-app/coach/terraform.tfstate`.
The in-cluster runner uses its service account for Kubernetes access and the
GitHub OIDC deploy role for AWS access. `TF_STATE_BUCKET` names the state bucket.
Network isolation has independent opt-in controls for workload and database
ingress and egress, external ServiceEntries and waypoint policy.

The app stack selects the ECR image tag from `image_tag` (default `latest`). CI
publishes `latest` for `master` and a branch-specific tag for other branches.
The workflow passes the same derived tag to Packer, the app stack and the
Coach stack. A full manual run
against `master`, with `apply_terraform=true` and both partial-build inputs
false, rebuilds its `latest` images and reapplies its infrastructure and Coach
states.

`core` installs the runner and `perms` grants it its permissions, so on a
brand-new cluster those two are applied once from a workstation before the
runner can take over.

## AWS workload identity

The [deployment workflow](../../.github/workflows/build-images.yml) publishes
the issuer metadata before changing k3s.

1. The in-cluster runner reads the API server's public RSA keys from
   `/openid/v1/jwks` and supplies them to the AWS Terraform plan and apply as
   `TF_VAR_workload_identity_jwks`. The AWS stack publishes the public keys
   and discovery document in S3, registers the IAM OIDC provider and creates
   the per-service roles. When k3s signing keys rotate, run the AWS deployment
   with the updated public key set so STS can verify newly signed tokens.
2. If the issuer needs to change, the runner submits a System Upgrade
   Controller Plan for the single control-plane node. The Plan configures k3s
   to issue tokens with the new issuer, retains the previous issuer for token
   validation and restarts k3s. CI checks discovery, API readiness and node
   readiness before applying the Kubernetes stacks.
3. App and Coach mount the AWS token into their workloads. After rollout, CI
   verifies that `pl-rankings` receives credentials for the expected AWS role
   and that STS rejects both a wrong audience and an unrelated service account.

The AWS stack's `workload_identity_issuer` output gives the public issuer URL.
For clusters migrating from a shared IAM key, the operator retires the old
key and SSM parameter after rollout verification.

To repeat the CI check from the repository root, use a kubeconfig with
TokenRequest permission and AWS credentials for the account lookup. The script
requires Python with `boto3`.

```bash
role_arn=$(kubectl -n powerlifting get deployment pl-rankings \
  -o jsonpath='{.spec.template.spec.containers[*].env[?(@.name=="AWS_ROLE_ARN")].value}')
python3 scripts/verify_workload_identity.py --namespace powerlifting \
  --region ca-central-1 --service-account pl-rankings --role-arn "$role_arn"
```

If role assumption succeeds but an S3 or DynamoDB call returns `AccessDenied`,
check the workload's allowed actions and resources in the
[IAM policy definitions](../workload_identity.tf). For an issuer or signature
error, compare the live k3s discovery document and public keys with the two
documents at the S3 issuer. See the [runtime trust chain](../../docs/ARCHITECTURE.md#aws-workload-identity).

## Authentik

`core` installs the CNPG operator, a two-instance Postgres cluster and the
Authentik Helm release in `namespace`, and runs the bootstrap job that
creates the `akadmin` API token from `authentik_bootstrap_token`. The same
stack configures Authentik through its API: the `nolift-powerlifting` OIDC
provider and application, the `athletes`/`coaches`/`handlers` roles and groups,
the scope mappings and the Discord identity source. Discord source matching uses
its verified provider identifier. The OIDC client ID and secret are written to
the `authentik-powerlifting-oidc` secret in `namespace`; the app stack copies
only the client secret to the OAuth proxy's secret.

CI runs the identity-pointer migration's preflight and conditional writes before
the app-stack apply; existing Person and Athlete keys are preserved. The backend media-signing private key is
read separately from `/powerlifting/media/cloudfront-signing-private-key`.

The Authentik provider connects to the in-cluster `authentik-server` service,
so on a new cluster Authentik is installed with a targeted apply first (see
below).

Both public hostnames use the configured Cloudflare tunnel origin, which points
to the NGINX Gateway Service. NGINX watches only `namespace`, and its Gateway
accepts routes only from `namespace`. The `auth` HTTPRoute reaches the
`authentik-server` Service in the same namespace. Apply the app stack
before the Coach stack so its waypoint and authorization provider exist.

## Monitoring

`core` runs the `monitoring` namespace: Prometheus, Loki, Promtail, Grafana,
node-exporter, cadvisor, kube-state-metrics and the event exporter. Promtail
ships container logs from `namespace` and `runner_namespace`.
Grafana is not exposed through the gateway; reach it with a port-forward at the
`grafana_url` output and log in as `admin` with `grafana_admin_password`:

```bash
kubectl -n monitoring port-forward svc/grafana 3000:3000
terraform -chdir=core output grafana_url
```

Dashboards are provisioned from `core/dashboards/` and the inline
container-logs dashboard.

## New cluster bootstrap

Run once from a workstation, then push to let the runner apply everything:

```bash
export KUBE_CONFIG_PATH=~/.kube/config
for stack in core perms; do
  terraform -chdir=$stack init -backend-config=../backend.tfvars -backend-config="key=powerlifting-app/k8s/$stack.tfstate"
done
terraform -chdir=core apply -var-file=../k8s.tfvars \
  -target=helm_release.authentik -target=kubernetes_job_v1.authentik_bootstrap_token
terraform -chdir=core apply -var-file=../k8s.tfvars
terraform -chdir=perms apply -var-file=../k8s.tfvars
```
