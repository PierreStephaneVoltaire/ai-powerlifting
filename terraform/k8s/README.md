# Kubernetes stacks

Four independent states, applied in order.

| Stack | Holds | Applied by |
|---|---|---|
| `core` | Namespaces, config, secrets, pod AWS credentials (read from SSM), registry pull secret, Actions runner controller and scale set, Authentik with its CNPG Postgres cluster and NoLift identity objects, monitoring (Prometheus, Loki, Promtail, Grafana, exporters) | Locally |
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

```bash
export KUBE_CONFIG_PATH=~/.kube/config
for stack in core perms network app; do
  terraform -chdir=$stack init -backend-config=../backend.tfvars -backend-config="key=powerlifting-app/k8s/$stack.tfstate"
  terraform -chdir=$stack apply -var-file=../k8s.tfvars
done
```
