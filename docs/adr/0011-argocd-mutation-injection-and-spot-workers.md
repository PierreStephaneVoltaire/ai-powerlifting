# ADR 0011 — Argo CD with Terraform mutation injection, and EC2 Spot workers over Tailscale

Date: 2026-11-25

## Status

Accepted

Implementation amendment, 2026-11-27: worker bootstrap and ongoing health checks
use Ansible through cloud-init. The home server uses a one-time Ansible playbook,
not a pipeline host script or automatic rollback. Argo manages the termination handler and reaper CronJob; Terraform retains generated secrets,
AWS resources and Argo application registration. The worker VPC CIDR is fixed
inside the module. the corresponding instructions below.

## Context

- **Slow deploys.** Every master push, and every push to a branch with an open PR, runs `kubernetes-apply` on the in-cluster runner. That job applies five Terraform states in sequence (`core perms network mesh app`), then Coach, then waits on every rollout. It took 9 minutes in the last successful master run. Images are resolved from tag to digest at apply time (`terraform/k8s/app/images.tf`).
- **Not enough compute.** The cluster is one k3s v1.34.5 node (16 CPU / 32 GiB). It is also the workstation and the CI runner disk. Memory limits are at 101%.
- **Rule for this document.** It lives in the public repo, so it names no host, LAN address, account ID or domain.
- **Private values.** The repo `PierreStephaneVoltaire/ai-powerlifting` is **public**. The only private values the workloads use are:
  - AWS account ID (in ECR image URLs and IAM role ARNs)
  - region
  - the app, auth and LLM domains
  - the home node hostname
  - bucket names
  - Coach Discord IDs

**Outcome:**

1. Argo CD and Image Updater are installed by Terraform. Argo tracks `master`.
2. Git holds plain manifests with **no private values**. Terraform generates the mutations and injects them into each Argo Application through the native `spec.source.kustomize.patches`. No custom plugin.
3. Rollouts happen when the **ECR digest** behind `latest` changes, not on commits.
4. Terraform provisions EC2 Spot workers in private subnets. They have no public IPs or direct inbound access and join the cluster over Tailscale. One ARM64 fck-nat instance in a dedicated public subnet provides IPv4 egress; the existing S3 gateway endpoint remains in place.
5. Istio Ambient, AWS workload identity (OIDC) and Authentik login keep working.

Crossplane is out of scope. It will be one more Argo Application later.

### Changes from the previous draft

- **No custom renderer.** The draft built a Config Management Plugin with a custom renderer. It is dropped: Argo already supports inline Kustomize patches in the Application spec. [Argo CD Kustomize](https://argo-cd.readthedocs.io/en/stable/user-guide/kustomize/)
- **No CRD deletion.** The draft deleted the leftover Argo CRDs. Live check: they carry `meta.helm.sh/release-name=argocd` / `argocd-image-updater` in namespace `argocd`, and 0 instances exist. Installing releases with those names in `argocd` adopts them.
- **Private workers.** Workers run in private subnets without public IPs or direct inbound access. A single ARM64 fck-nat instance in a dedicated public subnet provides IPv4 egress. Tailscale joins over outbound connectivity and can use direct paths or DERP relay.
- **Argo SSO is in scope.** The draft said "Authentik config is out of scope", but Authentik clients are already Terraform-managed (`terraform/k8s/core/litellm_identity.tf`). Argo SSO follows that pattern.
- **No manual tokens.** The draft relied on manually created tokens and console checks. Terraform now mints the k3s bootstrap token and the Tailscale key. The pipeline does every step.
- **Conversion is planned.** The draft ignored that every workload is HCL today. Converting them to YAML is the main work and is planned below.

---

## Part A — Argo CD with mutation injection

### A1. What moves to Argo, what stays in Terraform

| Moves to Git manifests (Argo)                                                                                                                             | Stays in Terraform                                                                                                                                                                    |
| --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform/k8s/app`: Deployments, Services, ServiceAccounts, waypoint, AuthorizationPolicies, PeerAuthentication, NetworkPolicies, non-private ConfigMaps | all `kubernetes_secret_v1`, `random_password`, `tls_private_key`, `aws_ssm_parameter`                                                                                                 |
| `terraform/coach`: Deployments, Services, ServiceAccounts, mesh and network policies                                                                      | PVCs, which Argo must never prune                                                                                                                                                     |
| `terraform/k8s/network`: HTTPRoutes, SnippetsFilters, cloudflared Deployment                                                                              | namespaces, Authentik (`authentik_*`), platform Helm releases (Istio, CNPG, Dapr, Authentik, gateway, ARC), monitoring stack, ECR refresher CronJob, `kubernetes_job_v1.litellm_keys` |
|                                                                                                                                                           | any ConfigMap or manifest that embeds a private value through a channel other than the four in A3                                                                                     |

The Git layout mirrors the stacks. Every folder has a `kustomization.yaml` that lists its resource files.

```
deploy/argocd/
  app/       kustomization.yaml, services.yaml, sessions.yaml, … , mesh.yaml, network-policy.yaml
  coach/     kustomization.yaml, agent.yaml, discord.yaml, mesh.yaml, network-policy.yaml
  network/   kustomization.yaml, routes.yaml, llm-route.yaml, tunnel.yaml
```

**Conversion rule.** Each HCL resource becomes the equivalent YAML. Keep names, labels, selectors, ports, probes, resources, strategies and projected token volumes. Translate `for_each` maps (for example `local.services` in `app/services.tf`) into one document per instance. `depends_on` ordering becomes `argocd.argoproj.io/sync-wave` annotations: mesh and network policies at `-1`, workloads at `0`.

### A2. Placeholders in Git (all non-private)

Manifests mark where a private value goes. Terraform scans these markers. It does **not** keep a separate list of targets.

| Marker in Git                                                                                                                                                                 | Terraform injects                                                                                                                                                                                       |
| ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Container `image: if-powerlifting-sessions` (bare ECR repository name, regex `^if-[a-z0-9-]+$`)                                                                               | Patch to `<account>.dkr.ecr.<region>.amazonaws.com/if-powerlifting-sessions:latest`, plus one ImageUpdater entry                                                                                        |
| Env value `nolift:private:<key>`, where `<key>` is one of `app_domain`, `auth_domain`, `llm_domain`, `region`, `dataset_bucket`, `reference_bucket`, `discord_operator_id`, … | Strategic-merge patch setting that env var's real value. Args that need the value use Kubernetes `$(VAR)` expansion, e.g. `--redirect-url=https://$(APP_DOMAIN)/oauth2/callback`                        |
| Pod label `nolift.io/aws-workload: "true"`                                                                                                                                    | Env patch with today's `module.workload_aws` output: `AWS_ROLE_ARN=arn:aws:iam::<acct>:role/nolift-<serviceAccountName>`, `AWS_WEB_IDENTITY_TOKEN_FILE`, `AWS_REGION`, … The token volume stays in Git. |
| Annotation `nolift.io/home-node: "true"` (pl-coach)                                                                                                                           | `nodeSelector: {kubernetes.io/hostname: <node_name>}`                                                                                                                                                   |
| HTTPRoute annotation `nolift.io/hostname: app\|auth\|llm\|argocd`                                                                                                             | JSON patch `replace /spec/hostnames`                                                                                                                                                                    |

### A3. Terraform stack `terraform/k8s/argocd`

This is a new state (`powerlifting-app/k8s/argocd.tfstate`), applied by the in-cluster runner after `app`. Split it into these files:

- `install.tf`
- `sso.tf`
- `manifests.tf` (scan)
- `mutations.tf`
- `applications.tf`
- `image_updater.tf`
- `variables.tf`

**Install (`install.tf`):**

- `helm_release.argocd`
  - argo-cd chart, release `argocd`, namespace `argocd`, pinned chart version. This adopts the existing CRDs.
  - Images: `quay.io/argoproj/argocd`. Redis comes from `public.ecr.aws/docker/library/redis`; override the chart if its default points elsewhere (no Docker Hub).
  - Dex disabled, ApplicationSet controller disabled, `server.insecure=true` (TLS ends at Cloudflare/gateway).
  - `configs.cm."timeout.reconciliation" = "0s"`: Argo does **not** poll Git. It re-renders when its Application spec changes (Terraform mutations, Image Updater digests) or when the pipeline annotates a refresh. This removes the race between a manifest change and its mutation (see C1).
- `helm_release.argocd_image_updater`
  - Release `argocd-image-updater`, namespace `argocd`, chart pinned to the release carrying image updater **v1.5.1**. Image `quay.io/argoprojlabs/argocd-image-updater`.
  - If the chart ships its CRD under `crds/` (Helm does not upgrade those), apply the v1.5.1 CRD with `kubectl_manifest` server-side, so the June 2026 schema is upgraded.
  - Registry config (in-cluster only):
    ```yaml
    registries:
      - name: ecr
        api_url: https://<acct>.dkr.ecr.<region>.amazonaws.com
        prefix: <acct>.dkr.ecr.<region>.amazonaws.com
        credentials: pullsecret:powerlifting/ecr-registry
        credsexpire: 5h
    ```
  - This reuses the existing `ecr-token-refresher` Secret, which is refreshed every 6h and valid for 12h. Add a Role and RoleBinding letting the updater's ServiceAccount `get` that one Secret.

**Manifest scan (`manifests.tf`):**

```hcl
locals {
  argocd_apps = toset(["app", "coach", "network"])
  docs = { for app in local.argocd_apps : app => flatten([
    for f in fileset("${local.deploy_root}/${app}", "*.yaml") : [
      for d in split("\n---\n", file("${local.deploy_root}/${app}/${f}")) : yamldecode(d)
      if f != "kustomization.yaml" && trimspace(d) != ""
    ]
  ]) }
}
```

From `local.docs` derive per app:

- `workloads`: Deployments with container names, images, env placeholders and markers
- `routes`
- `ecr_repos`: the distinct bare image names

A `precondition` fails the plan when:

- a placeholder key is missing from `local.private_values`, or
- a `nolift.io/aws-workload` pod has no matching `data.aws_iam_role` (the role name is `nolift-<sa>`, already created by the AWS root).

**Mutations (`mutations.tf`):** one list of `{target, patch}` per app. Strategic-merge patches merge `containers` and `env` by `name`, so no array indexes are used.

```hcl
image_patches = [for w in local.workloads[app] : {
  target = { kind = "Deployment", name = w.name }
  patch = yamlencode({
    apiVersion = "apps/v1", kind = "Deployment", metadata = { name = w.name }
    spec = { template = { spec = { containers = [
      for c in w.containers : merge(
        { name = c.name },
        can(regex("^if-[a-z0-9-]+$", c.image)) ? { image = "${local.ecr}/${c.image}:latest" } : {},
        { env = concat(
            [for e in c.private_env : { name = e.name, value = local.private_values[e.key] }],
            w.aws ? [for k, v in module.workload_aws[w.sa].env : { name = k, value = v }] : [])
        }
      )
    ] } } }
  })
}]
```

`module.workload_aws` is moved here from `app/workload_identity.tf` unchanged.

**Applications (`applications.tf`):**

- One `kubectl_manifest` per app, with `server_side_apply = true` and `field_manager = "terraform"`. Terraform therefore **never owns** `spec.source.kustomize.images`, which Image Updater writes.
- AppProject `nolift`: source repo is the public repo only, destination namespace `powerlifting`, no cluster-scoped resources.

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata: { name: nolift-app, namespace: argocd }   # no resources-finalizer: deleting the Application never deletes workloads
spec:
  project: nolift
  destination: { server: https://kubernetes.default.svc, namespace: powerlifting }
  source:
    repoURL: https://github.com/PierreStephaneVoltaire/ai-powerlifting.git
    targetRevision: master
    path: deploy/argocd/app
    kustomize:
      patches: <local.mutations.app>     # Terraform-owned
      # images: written by Image Updater only
  syncPolicy:
    automated: <var.argocd_auto_sync ? {prune: true, selfHeal: true} : null>
    syncOptions: [ServerSideApply=true, PruneLast=true]
```

Kustomize runs `patches` before `images`. So the Terraform image patch (`<ecr>/repo:latest`) is a valid fallback, and Image Updater's override pins the digest. A missing override never renders a Docker Hub name.

**Image Updater (`image_updater.tf`):** one `ImageUpdater` per app, generated from `ecr_repos`. Each repository appears once, even when several Deployments share it (e.g. `if-powerlifting-fns`).

```yaml
apiVersion: argocd-image-updater.argoproj.io/v1alpha1
kind: ImageUpdater
metadata: { name: nolift-app, namespace: argocd }
spec:
  writeBackConfig: { method: argocd }
  applicationRefs:
    - namePattern: nolift-app
      images:
        - alias: powerlifting-sessions
          imageName: <ecr>/if-powerlifting-sessions:latest
          commonUpdateSettings: { updateStrategy: digest }
          manifestTargets:
            { kustomize: { name: <ecr>/if-powerlifting-sessions } }
```

**SSO (`sso.tf` plus `core` and `network`):**

- **Authentik client.** `authentik_provider_oauth2.argocd` and `authentik_application.argocd` copy the shape of `core/litellm_identity.tf`. Redirect: `https://${var.argocd_domain}/auth/callback`. Add a group `argocd-admins` with members from `var.argocd_admins`, like `litellm_admins`.
- **Argo config.**
  - `configs.cm."oidc.config"` points at `https://${var.auth_domain}/application/o/argocd/`, client `nolift-argocd`, `requestedScopes: [openid, profile, email, groups]`.
  - The client secret goes into `argocd-secret` as `oidc.authentik.clientSecret`.
  - `configs.rbac`: `policy.default: ""`, `g, argocd-admins, role:admin`, `scopes: [groups]`.
  - `admin.enabled: false`.
- **Exposure.**
  - New HTTPRoute `argocd` in `network`, plus a ReferenceGrant from `argocd` to `argocd-server:80`.
  - New tunnel hostname in `terraform/modules/tunnel` and `terraform/main.tf`, copying the `llm_hostname` wiring.
  - New variable `argocd_domain` in `TF_VAR_*` and `K8S_TFVARS`.

### A4. Handoff from Terraform to Argo with no restarts

Run as **PR 1**, inside the normal pipeline, with `argocd_auto_sync = false`.

1. Apply the `argocd` stack. Argo, Image Updater, the Applications (manual sync) and the ImageUpdaters now exist.
2. `scripts/argocd_handoff.sh` (pipeline step, idempotent) seeds images:
   - For each Application whose `spec.source.kustomize.images` is empty, read each live Deployment's current `repo@sha256` image.
   - `kubectl patch application … --type merge` the matching `images` entries.
   - The first render therefore equals what is running. This is the "pipeline updates it" fallback.
3. **Gate.** `argocd app diff <app> --core --exit-code` (the CLI in core mode uses the runner's kubeconfig). Fail the job if any Deployment `spec.template` differs. Only metadata such as the tracking annotation may differ.
4. Run `argocd app sync <app> --core` for each app. Argo adopts the live objects with server-side apply.
5. Remove the moved objects from Terraform state, without destroying them:
   - For `app`, `coach` and `network`, run `terraform plan -json`.
   - For every planned **delete** whose live object now carries `argocd.argoproj.io/tracking-id`, run `terraform state rm <addr>` (CLI; no `removed {}` blocks).
   - Re-plan and fail if any delete remains.
6. Apply `app`, `coach` and `network`. They now only own secrets, PVCs, platform resources and private ConfigMaps.

**PR 2** sets `argocd_auto_sync = true`, deletes `argocd_handoff.sh`, removes `var.image_tag` and `data.aws_ecr_image` from `app` and `coach`, and makes the pipeline changes in C1.

**Rollback before PR 2:** delete the Applications (no finalizer, so the workloads stay running), restore the HCL from git history, and `terraform import` the objects (CLI, run by the pipeline).

---

## Part B — Private EC2 Spot workers over Tailscale

### B1. Tailscale (Personal plan is enough)

The Personal plan includes 6 users and 50 tagged devices. Ephemeral nodes are metered at 1,000 minutes per month, so workers are **not** ephemeral; a reaper cleans up stale devices instead (B4). Standard is not needed. [Tailscale pricing](https://tailscale.com/pricing)

**One-time account input** (the only operator action, like the Cloudflare token): a Tailscale OAuth client with scopes `policy_file`, `oauth_keys`, `auth_keys`, `devices:core`, `dns`, stored as CI secrets `TAILSCALE_OAUTH_CLIENT_ID` / `TAILSCALE_OAUTH_CLIENT_SECRET`.

Terraform provider `tailscale/tailscale` (~> 0.30), in the new k8s stack `terraform/k8s/nodes`:

- `tailscale_acl.policy`
  - If the tailnet already has a policy, the pipeline imports it once, idempotently: `terraform state list | grep -q tailscale_acl.policy || terraform import tailscale_acl.policy acl`. Its existing rules are carried into the HCL.
  - Adds `tagOwners` for `tag:k3s-server` and `tag:k3s-worker`.
  - Adds a grant `tag:k3s-* → tag:k3s-*` on all ports. That covers 6443, 10250 and VXLAN 8472, plus hostNetwork scrapes.
  - Workers get no access to personal devices.
- `tailscale_dns_preferences { magic_dns = true }`
- `tailscale_oauth_client.worker_join`
  - Scope `auth_keys`, tag `tag:k3s-worker`.
  - Its secret is used directly as a non-expiring auth key: `<secret>?ephemeral=false&preauthorized=true`.
  - Stored in SSM `/nolift/k3s/tailscale-worker-key` (SecureString).
- `tailscale_oauth_client.server_join` (tag `tag:k3s-server`), stored as a Secret in `cattle-system` for the server Plan.
- `tailscale_oauth_client.reaper`, scope `devices:core`.

### B2. Home server joins the tailnet (gated, with automatic rollback)

Use the existing host-mutation pattern: a system-upgrade-controller `Plan`, like `scripts/k3s-workload-identity-plan.sh` and `-host.sh`, but rendered by Terraform in the `nodes` stack. Its node selector is the control-plane label, so no hostname appears in Git. Use a `public.ecr.aws/docker/library/alpine` image.

The host script `scripts/k3s-tailnet-host.sh`, running under chroot `/host`:

1. Install Tailscale from its apt repo if missing. Run `tailscale up --auth-key=$KEY?preauthorized=true --advertise-tags=tag:k3s-server --hostname=nolift-k3s-server --port=41641`, then `tailscale set --auto-update=false`.
2. Back up `config.yaml.d/`. Write `zzzz-nolift-tailnet.yaml`, which sets the node IP to the Tailscale address so the API advertise address, kubelet and flannel all move to the tailnet. Every value is computed when the script runs; none is in Git:
   ```yaml
   node-ip: <tailscale ip -4>
   flannel-iface: tailscale0
   tls-san: [nolift-k3s-server, <tailscale ip -4>, <current LAN InternalIP>]
   ```
   Keeping the LAN address in `tls-san` preserves LAN access to the API.
3. Add systemd drop-ins:
   - `k3s.service`: `After=tailscaled.service`, `Wants=tailscaled.service`
   - `tailscaled.service`: `ExecStartPost=/bin/systemctl try-restart k3s.service`
   - Reason: flannel binds VXLAN to the `tailscale0` ifindex, which a tailscaled restart recreates.
4. Restart k3s. Poll `/readyz` and node `Ready` for 180 s. **On failure, restore the backup and restart k3s.**

Pods keep running across a k3s restart, because containerd is untouched. Pod MTU becomes about 1230 (1280 − 50 VXLAN) for pods created afterwards.

The `nodes` stack also writes these SSM parameters, so the AWS side never needs cluster values:

- `/nolift/k3s/server-url` = `https://nolift-k3s-server:6443`
- `/nolift/k3s/version` = the server's `kubeletVersion`, read from the node
- `/nolift/k3s/agent-token` (SecureString). This is a bootstrap token:
  - `random_string` id (6) and secret (16)
  - `kubernetes_secret_v1` named `bootstrap-token-<id>` in `kube-system`, type `bootstrap.kubernetes.io/token`, with `usage-bootstrap-authentication=true`, `usage-bootstrap-signing=true`, `auth-extra-groups=system:bootstrappers:k3s:default-node-token`
  - Value `K10<sha256(GET /cacerts)>::<id>.<secret>`. The CA hash is read with `data "http"` from the supervisor's `/cacerts`, so the agent pins the server CA. [k3s token](https://docs.k3s.io/cli/token)

### B3. AWS module `terraform/modules/k3s_workers` (AWS root, applied by CI)

| Variable                                       | Default                                                                              | Purpose                                                                                                                              |
| ---------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------ |
| `workers_enabled`                              | `false`                                                                              | Master switch for the whole module (`count`)                                                                                         |
| `worker_vpc_cidr`                              | `10.60.0.0/16`                                                                       | Validated not to overlap 10.42/16 (pods), 10.43/16 (services), `var.home_lan_cidr` (private tfvars, no default), 100.64/10 (tailnet) |
| `worker_azs`                                   | `["ca-central-1a","ca-central-1b","ca-central-1d"]`                                  | One private /24 per AZ                                                                                                               |
| `worker_min` / `worker_desired` / `worker_max` | `0 / 0 / 3`                                                                          | Validated `min ≤ desired ≤ max`                                                                                                      |
| `worker_instance_types`                        | `["m6a.large","m6i.large","m5a.large","m5.large","m7i.large"]`                          | 2 vCPU / 8 GiB amd64; the images are amd64                                                                                           |
| `worker_ami_ssm_parameter`                     | `/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id` | Ubuntu 24.04, same as the server                                                                                                     |
| `worker_root_volume_gib`                       | `40`                                                                                 | Encrypted gp3                                                                                                                        |
| `worker_spot_max_price`                        | `null`                                                                               | `null` means pay up to the on-demand price                                                                                           |

**Resources:**

- **Network.**
  - Private worker subnets with no public IP assignment, plus one dedicated public subnet for an ARM64 fck-nat instance.
  - Private subnet default routes use fck-nat for IPv4 egress. The existing S3 gateway endpoint remains for ECR layers.
  - No worker inbound rules, SSH or port 22. Tailscale can establish direct connectivity where outbound paths allow it, or use DERP relay.
- **Security group.** No inbound rules; all outbound allowed.
- **IAM instance role.**
  - `ssm:GetParameter(s)` on `arn:aws:ssm:<region>:<acct>:parameter/nolift/k3s/*`
  - `AmazonSSMManagedInstanceCore`, for Session Manager debugging
  - **No** ECR, S3 or Dynamo access. Pods keep using projected workload identity, and ECR pulls use the existing `ecr-registry` pull secret.
- **Launch template.**
  - `metadata_options { http_tokens = "required", http_put_response_hop_limit = 1 }`. The hop limit of 1 means pods cannot reach instance credentials.
  - `instance_initiated_shutdown_behavior = "terminate"`.
  - `user_data` comes from `templatefile("worker-init.sh.tftpl", {region})`. It contains no secrets and no cluster values.
- **Auto Scaling group.**
  - `mixed_instances_policy`: `on_demand_base_capacity = 0`, `on_demand_percentage_above_base_capacity = 0`, `spot_allocation_strategy = "price-capacity-optimized"`.
  - `capacity_rebalance = true`, instance refresh on launch-template change.
  - Termination lifecycle hook with a 300 s heartbeat, so nodes drain on scale-in (B4).
- **Interruption events.** SQS queue plus EventBridge rules (Spot interruption, rebalance recommendation, ASG lifecycle, instance state-change) for node-termination-handler (NTH).

**`worker-init.sh.tftpl` at boot:**

1. Read the four `/nolift/k3s/*` parameters with the instance role. Retry for up to 20 min, so a desired count above 0 before the `nodes` stack exists does not fail-loop.
2. Install Tailscale and run `tailscale up --auth-key=… --advertise-tags=tag:k3s-worker --hostname=nolift-k3s-<instance-id> --port=41641`. Add the same `ExecStartPost` drop-in pointing at `k3s-agent`.
3. Write `/etc/rancher/k3s/config.yaml`, then install k3s with `INSTALL_K3S_VERSION=$(version) INSTALL_K3S_EXEC=agent` from get.k3s.io:
   ```yaml
   server: <server-url>
   token-file: /etc/rancher/k3s/agent-token
   node-ip: <tailscale ip -4>
   flannel-iface: tailscale0
   pause-image: registry.k8s.io/pause:3.9
   node-label: [nolift.io/pool=aws-spot, topology.kubernetes.io/zone=<az>]
   node-taint: [nolift.io/pool=aws-spot:NoSchedule]
   kubelet-arg: [provider-id=aws:///<az>/<instance-id>, max-pods=110]
   ```
4. **Join watchdog.** If the node is not `Ready` 15 min after boot (checked with the agent's kubelet kubeconfig), run `shutdown -h now`. The ASG then replaces the instance, so a worker that never joins does not keep running and billing.

### B4. Cluster side (`terraform/k8s/nodes` + `core`)

- **Spot interruptions and scale-in.** `helm_release.nth`: aws-node-termination-handler in queue mode, from `oci://public.ecr.aws/aws-ec2/helm/aws-node-termination-handler`.
  - `enableSqsTerminationDraining`, `useProviderId: true`.
  - AWS access through the existing workload-identity pattern: a new IAM role `nolift-aws-node-termination-handler` in `terraform/workload_identity.tf` with `sqs:ReceiveMessage/DeleteMessage`, `autoscaling:CompleteLifecycleAction` and `ec2:DescribeInstances`.
  - It cordons and drains the node on interruption, rebalance or scale-in, then completes the lifecycle hook.
- **Reaper.** A `kubernetes_cron_job_v1` named `node-reaper`, every 10 min, using the same `public.ecr.aws/aws-cli/aws-cli` + curl/jq pattern as `ecr-token-refresher`. It deletes `nolift.io/pool=aws-spot` Nodes that have been NotReady for more than 10 min, and `tag:k3s-worker` Tailscale devices that have been offline for more than 10 min.
- **DaemonSets.**
  - `istio-cni-node` and `ztunnel` must run on workers. Check their chart tolerations and add `operator: Exists` in `mesh/main.tf` if the defaults don't already tolerate all `NoSchedule` taints.
  - Do the same for `node_exporter`, `cadvisor` and `promtail` in `core`.
- **Scheduling policy.** Workers are tainted, so nothing moves unless it opts in.
  - Stateful pods cannot move: local-path PV node affinity keeps the 14 PVC-backed pods home, and pl-coach is pinned.
  - Opt-in happens in Git: a toleration plus a _preferred_ node affinity for `nolift.io/pool=aws-spot`. Pods run on Spot when capacity exists and fall back home at desired = 0.
  - First candidates: `pl-rankings`, `pl-analytics`, `pl-analytics-ai`, `pl-analytics-export`, `pl-export`, and the ARC runner scale set.
  - Authentik, the CNPG databases, valkey, litellm and the gateway stay home, because they are chatty with home-node state.

### B5. Rollout order

1. **PR 3:** `nodes` stack. Tailnet ACL and keys, server Plan, SSM parameters, NTH, reaper, DaemonSet tolerations. Workers are still disabled.
2. **PR 4:** AWS module with `workers_enabled = true` and `worker_desired = 0`.
3. Set `worker_desired = 1` in tfvars, then verify (section D).
4. **PR 5:** add opt-in tolerations to the candidate manifests in `deploy/argocd`. Raise the count when needed.

**Approximate cost per worker** (ca-central-1; check the AWS pricing pages):

- m6a.large Spot ≈ $25/mo
- 40 GiB gp3 ≈ $3.50/mo
- internet egress to home over Tailscale at $0.09/GB after 100 GB/mo
- shared fck-nat instance and its IPv4 egress

Tailscale is $0.

---

## Part C — Pipeline (`.github/workflows/build-images.yml`)

### C1. Changes

- **Builds are unchanged.** Master pushes publish `latest`; branch pushes publish `branch-*`.
- **No Terraform for code pushes.** `kubernetes-apply` no longer depends on the build jobs. It runs only when the `kubernetes` filter matches (add `deploy/argocd/**`), and **only on master**. PR branches no longer deploy to the live cluster. That is a behavior change, and it follows from "Argo points to master".
- **Stack order** becomes `core perms network mesh app argocd nodes`, then Coach. The `argocd` and `nodes` states use the same `-backend-config` loop.
- **New env.** `TAILSCALE_OAUTH_CLIENT_ID` / `TAILSCALE_OAUTH_CLIENT_SECRET` (provider env), and `TF_VAR_argocd_domain` for the AWS root.
- **Let Argo reconcile.** Applying the Application specs is sufficient for auto-sync. Keep the independent Istio and projected AWS trust checks.
- **Remove deploy-frontend-only** (job `deploy-frontend-only` in `build-images.yml`). Image Updater deploys the frontend.
- **Remove `image_tag` from the k8s stacks.** Drop `-var image_tag` from the `app` and Coach applies.
- **Leave `pull-requests.yml` alone.**

### C2. Resulting flow

```
push master (src/**) → GitHub-hosted build → ECR :latest digest changes → Image Updater (≤2 min poll)
                     → writes Application kustomize.images → Argo renders master + Terraform patches → rollout
push master (terraform/k8s/** or deploy/argocd/**) → in-cluster runner applies changed state(s)
                     → mutations regenerated from the same checkout → Argo auto-sync
```

---

## D. Verification

Every check runs in the pipeline or is read-only. No full test suites.

**Argo and mutations**

- **Render check** (pipeline, before sync): `argocd app manifests nolift-<app> --core --source live`. Fail on any of these in the output:
  - `nolift:private:`
  - a bare `image: if-`
  - an image without `@sha256:` once the images are seeded
- **Handoff gate:** `argocd app diff --core` shows no pod-template change. Restart counts stay the same after the sync (`kubectl get pods -n powerlifting`).
- **Mutation:** change one private input (e.g. `node_name` in `COACH_TFVARS`) with Git unchanged. `argocd app diff` shows only that field.
- **Digest:** push a master build of one service. Within about 2 min, the Application's `kustomize.images` shows the new digest and only that Deployment rolls. Re-running the same digest causes no rollout. A Terraform re-apply leaves `kustomize.images` unchanged (server-side apply ownership).
- **Rollback:** re-tag the previous digest as `latest` in ECR, and the running image follows. ECR keeps the last 5 images; some repos expire untagged images after 1 day.
- **SSO:** log in at `https://<argocd_domain>` through Authentik as a member of `argocd-admins`. `admin` login is refused. Users outside the group have no permissions.
- **App OIDC unchanged:** `node scripts/test-auth-session.mjs`, then `node scripts/test-live-api.mjs`, and the existing `scripts/verify_workload_identity.py` step.

**Workers** (with `worker_desired = 1`)

- **Join:** `kubectl get nodes -o wide` shows the worker `Ready` with a 100.x InternalIP and the `aws-spot` taint. Tailscale ping succeeds over a direct path or DERP relay.
- **Networking:** start a disposable `public.ecr.aws/docker/library/busybox` pod tolerating the taint and pinned to the worker. Check:
  - DNS works (`nslookup kubernetes.default`)
  - ClusterIP reachability
  - HTTP to a home-node Service
  - a large transfer (`wget` of a multi-MB object from a home Service), to catch MTU blackholes
- **Istio Ambient:**
  - `istio-cni-node` and `ztunnel` are Ready on the worker.
  - A test pod in the ambient namespace with an allowed caller identity reaches a `pl-*` Service across nodes.
  - A disallowed identity is denied by the existing AuthorizationPolicies.
  - `scripts/verify_network_canary.py` passes.
- **AWS OIDC from the worker:** move `pl-rankings` there via the opt-in. `verify_workload_identity.py --service-account pl-rankings` passes, and a cold ECR pull succeeds. From the pod, `curl -m2 http://169.254.169.254` must fail (hop limit 1).
- **Lifecycle:**
  - Set `worker_desired = 0`: NTH drains the node, the lifecycle hook completes, and the reaper removes the Node and the Tailscale device. Opt-in pods fall back to the home node.
  - Set it back to 1: a fresh join works.
  - Send a simulated Spot interruption (AWS FIS or a test SQS message): the node drains.
- **Server rollback path:** for a dry run, run the Plan with a forced `/readyz` failure flag. The backup config is restored and the API returns.

## Critical files

- **New:**
  - `deploy/argocd/{app,coach,network}/*`
  - `terraform/k8s/argocd/*`, `terraform/k8s/nodes/*`
  - `terraform/modules/k3s_workers/*` (incl. `worker-init.sh.tftpl`)
  - `scripts/argocd_handoff.sh` (removed in PR 2), `scripts/k3s-tailnet-host.sh`
- **Edited:**
  - `terraform/main.tf`, `terraform/variables.tf` (worker module and variables, `argocd_domain`)
  - `terraform/modules/tunnel/*` (argocd hostname)
  - `terraform/workload_identity.tf` (NTH and reaper roles)
  - `terraform/k8s/core/{logs,metrics}.tf` (tolerations), `terraform/k8s/core/litellm_identity.tf` pattern copied for Argo
  - `terraform/k8s/mesh/main.tf` (tolerations if needed), `terraform/k8s/network/*` (Argo route)
  - `terraform/k8s/app/*` and `terraform/coach/*` (workloads deleted after handoff; `images.tf` removed)
  - `.github/workflows/build-images.yml`, `.github/image-filters.yml`
- **Reused:**
  - `terraform/k8s/modules/workload-aws` (env contract)
  - the `ecr-token-refresher` Secret
  - the system-upgrade-controller Plan pattern from `scripts/k3s-workload-identity-*.sh`
  - the Authentik client pattern from `core/litellm_identity.tf`
  - `scripts/verify_workload_identity.py`, `scripts/verify_network_canary.py`, `scripts/test-auth-session.mjs`
