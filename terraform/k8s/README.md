# Kubernetes stacks

The `kubernetes-apply` job on the in-cluster Actions runner applies core, perms,
network, mesh and app after their images are published. When Coach images build,
the same runner then applies Coach's separate state.

| Stack | Holds |
|---|---|
| `core` | Namespaces, config, secrets, pod AWS credentials (read from SSM), registry pull secret, Actions runner controller and scale set, Authentik and its CNPG Postgres cluster, NoLift identity objects in Authentik, monitoring |
| `perms` | Service accounts, roles and bindings (registry refresher, runner deployer bound to `cluster-admin`) |
| `network` | Gateway API CRDs, NGINX Gateway and data plane, app and Authentik routes, cloudflared, narrow Authentik `ReferenceGrant` |
| `mesh` | Pinned Istio Ambient base, control plane, CNI and ztunnel |
| `app` | `pl-*` services, analytics, Valkey, portal backend and frontend, registry token refresher |

The job runs only on protected branches, for pushes or manual applies triggered
by the repository owner. Manual apply defaults to disabled.
It writes `K8S_TFVARS` (the full `k8s.tfvars`, see `k8s.tfvars.example`) to a
temporary file. It applies `core`, `perms`, `network`, `mesh`, then `app`. It
applies Coach with `COACH_TFVARS` after a successful Coach image build. The
Coach state key remains `powerlifting-app/coach/terraform.tfstate`. The in-cluster runner uses its
service account for Kubernetes access. `TF_STATE_BUCKET` names the state bucket
and AWS reads go through the OIDC deploy role. App workloads use dedicated
service accounts and use Ambient enrollment. The pods' AWS key belongs to the scoped
`powerlifting-pods` IAM user, created outside terraform and stored in SSM at
`/powerlifting/k8s/aws-credentials`; no AWS key lives in any tfvars file or
terraform state.

The app stack selects the ECR image tag from `image_tag` (default `latest`). CI
publishes `latest` only for `master`; other protected branches publish their
branch-specific tag. The workflow passes the same derived tag explicitly to
Packer, the app stack and the Coach stack, overriding any value in tfvars. Run
the workflow manually against a protected feature branch to deploy it. A full manual run
against `master`, with `apply_terraform=true` and both partial-build inputs
false, rebuilds its `latest` images and reapplies its infrastructure and Coach
states. Keep the existing rollback credential inputs in `K8S_TFVARS` and
`COACH_TFVARS`; the new runtime does not use the old shared-token secret.

`core` installs the runner and `perms` grants it its permissions, so on a
brand-new cluster those two are applied once from a workstation before the
runner can take over.

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
