# Kubernetes stacks

Four independent states, applied in order.

| Stack | Holds | Applied by |
|---|---|---|
| `core` | Namespaces, config, secrets, pod AWS credentials (read from SSM), registry pull secret, Actions runner controller and scale set, Authentik and its CNPG Postgres cluster, NoLift identity objects in Authentik, monitoring | Locally |
| `perms` | Service accounts, roles and bindings (registry refresher, deployer) | Locally |
| `network` | Gateway controller, Gateway, routes, cloudflared | Runner |
| `app` | `pl-*` services, analytics, Valkey, portal backend and frontend, registry token refresher | Runner |

`core` and `perms` hold every secret and the runner's own permissions, so they
are only applied from the operator's machine with the full `k8s.tfvars`.
The pods' AWS key belongs to the scoped `powerlifting-pods` IAM user, created
outside terraform and stored in SSM at `/powerlifting/k8s/aws-credentials`; no AWS
key lives in any tfvars file or terraform state.

CI applies `network` and `app` from the `kubernetes-apply` job on the in-cluster
runner, only for pushes or manual runs triggered by the repository owner. Those
two stacks take no secrets: the `K8S_TFVARS` repository variable holds their
non-secret values (`region`, `namespace`, `app_domain`, `storage_class`,
`dataset_bucket`, `repositories`) and `TF_STATE_BUCKET` names the state bucket.
AWS reads go through the OIDC deploy role.

## Authentik

`core` installs the CNPG operator, a two-instance Postgres cluster and the
Authentik Helm release in `auth_namespace`, and runs the bootstrap job that
creates the `akadmin` API token from `authentik_bootstrap_token`. The same
stack configures Authentik through its API: the `nolift-powerlifting` OIDC
provider and application, the `athletes`/`coaches`/`handlers` roles and groups,
the scope mappings and the Discord login source. The client ID and secret are
written to the `authentik-powerlifting-oidc` secret.

The Authentik provider connects to the in-cluster `authentik-server` service,
so on a cluster where Authentik is not running yet, apply it before the rest:

```bash
terraform -chdir=core apply -var-file=../k8s.tfvars \
  -target=helm_release.authentik -target=kubernetes_job_v1.authentik_bootstrap_token
```

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

## Apply

```bash
export KUBE_CONFIG_PATH=~/.kube/config
for stack in core perms network app; do
  terraform -chdir=$stack init -backend-config=../backend.tfvars -backend-config="key=powerlifting-app/k8s/$stack.tfstate"
  terraform -chdir=$stack apply -var-file=../k8s.tfvars
done
```
