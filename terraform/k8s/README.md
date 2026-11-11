# Kubernetes stacks

The `kubernetes-apply` job on the in-cluster Actions runner applies core, perms,
network, mesh and app after their images are published. Coach resources remain a
local operator apply.

| Stack | Holds |
|---|---|
| `core` | Namespaces, config, secrets, pod AWS credentials (read from SSM), registry pull secret, Actions runner controller and scale set, Authentik and its CNPG Postgres cluster, NoLift identity objects in Authentik, monitoring |
| `perms` | Service accounts, roles and bindings (registry refresher, runner deployer bound to `cluster-admin`) |
| `network` | Gateway controller, Gateway, routes, cloudflared |
| `mesh` | Pinned Istio Ambient base, control plane, CNI and ztunnel |
| `app` | `pl-*` services, analytics, Valkey, portal backend and frontend, registry token refresher |

The job runs only for pushes or manual runs triggered by the repository owner.
It writes `K8S_TFVARS` (the full `k8s.tfvars`, see `k8s.tfvars.example`) to a
temporary file. It applies `core`, `perms`, `network`, optionally `mesh`, then
`app`. It does not apply Coach resources. The in-cluster runner uses its
service account for Kubernetes access. `TF_STATE_BUCKET` names the state bucket
and AWS reads go through the OIDC deploy role. App workloads use dedicated
service accounts and use Ambient enrollment. The pods' AWS key belongs to the scoped
`powerlifting-pods` IAM user, created outside terraform and stored in SSM at
`/powerlifting/k8s/aws-credentials`; no AWS key lives in any tfvars file or
terraform state.

`core` installs the runner and `perms` grants it its permissions, so on a
brand-new cluster those two are applied once from a workstation before the
runner can take over.

## Authentik

`core` installs the CNPG operator, a two-instance Postgres cluster and the
Authentik Helm release in `auth_namespace`, and runs the bootstrap job that
creates the `akadmin` API token from `authentik_bootstrap_token`. The same
stack configures Authentik through its API: the `nolift-powerlifting` OIDC
provider and application, the `athletes`/`coaches`/`handlers` roles and groups,
the scope mappings and the Discord login source. The client ID and secret are
written to the `authentik-powerlifting-oidc` secret.

The Authentik provider connects to the in-cluster `authentik-server` service,
so on a new cluster Authentik is installed with a targeted apply first (see
below).

## Monitoring

`core` runs the `monitoring` namespace: Prometheus, Loki, Promtail, Grafana,
node-exporter, cadvisor, kube-state-metrics and the event exporter. Promtail
ships container logs from `namespace`, `runner_namespace` and `auth_namespace`.
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
