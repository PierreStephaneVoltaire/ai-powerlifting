# NoLift mesh cutover

The implementation plan is [nolift-authentik-istio-migration-plan.md](../nolift-authentik-istio-migration-plan.md).
This branch requires Istio and Authentik-backed browser login. It has no legacy
authentication mode. These commands are for the operator; the implementation
agents do not apply Terraform, modify live identities or perform Git operations.

## Prepare

1. Reserve a maintenance window and stop new portal writes and Coach submissions.
   Let active work finish before replacing its runtime.
2. Record deployed image digests and the current application/Authentik hostnames.
   Keep the public Authentik issuer and existing provider subject configuration.
3. Inspect the node's actual K3s CNI configuration and paths. The chart uses the
   K3s platform profile; check it against the running CNI before installation.
4. Ensure the in-cluster runner can pull the pinned Helm charts and proxy image.
   Review shared Gateway API CRD changes against all installed controllers.
5. Preserve existing `K8S_TFVARS`, `COACH_TFVARS`, `AUTH_ORIGIN_URL` and other
   master deployment inputs. Keep the old shared-secret inputs for master's
   reapply. Core retains their existing Terraform resources and values, unused
   by the new runtime. Coach retains its separate state and variables.

Read-only baseline:

```bash
kubectl get nodes -o wide
kubectl top nodes
kubectl get deployments,pods,services -n powerlifting -o wide
kubectl get gateways,httproutes -A
kubectl get events -n powerlifting --field-selector type=Warning --sort-by=.lastTimestamp
```

Do not label the shared `if-portals` namespace for Ambient or restart unrelated
workloads. CNI changes still share the physical node with them.

## Provision the signing key

The application stack reads these existing SSM parameters in its configured AWS
region. The operator creates them once before planning the application stack:

```bash
umask 077
nolift_key_dir=$(mktemp -d)
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:3072 -out "$nolift_key_dir/private.pem"
openssl pkey -in "$nolift_key_dir/private.pem" -pubout -out "$nolift_key_dir/public.pem"
aws ssm put-parameter --region ca-central-1 --name /powerlifting/security/principal-signing-private-key --type SecureString --value "file://$nolift_key_dir/private.pem" --query Version --output text
aws ssm put-parameter --region ca-central-1 --name /powerlifting/security/principal-signing-public-key --type String --value "file://$nolift_key_dir/public.pem" --query Version --output text
```

Keep the private key and Terraform state access restricted. Do not print keys,
tokens, session cookies or request bodies in deployment evidence. Existing
parameters must contain a matching pair; do not rotate only one parameter.

## Deploy the coordinated release

Build images and run the repository checks before starting the window. Review
Terraform plans for `core`, `perms`, `network`, `mesh`, `app` and the separate
Coach stack. Reject plans that delete AWS resources or change unrelated workloads.

The Kubernetes workflow manages `core → perms → network → mesh → app`. Its mesh
state key is `powerlifting-app/k8s/mesh.tfstate`. The mesh state owns Istio;
the application state owns the waypoint, authorizer, proxy and portal policies.
The in-cluster runner then applies Coach's existing separate state after a
successful Coach image build, using `COACH_TFVARS`. This preserves the existing
master pipeline's deployment and rollback behavior.

Run the workflow with the feature branch selected, `apply_terraform=true`,
`backend_only=false` and `frontend_only=false`. All six images use one tag
derived from that branch (`python3 scripts/image_tag.py <branch>`). Only
`master`/`main` select `latest`; feature builds never publish it. The app and
Coach Terraform applies receive the same tag explicitly and resolve its digest.

For a workstation review of the new state and the separate Coach state:

```bash
umask 077
terraform -chdir=terraform/k8s/mesh init -backend-config=../backend.tfvars -backend-config=key=powerlifting-app/k8s/mesh.tfstate
terraform -chdir=terraform/k8s/mesh plan -var-file=../k8s.tfvars -out=mesh.tfplan
terraform -chdir=terraform/coach init -backend-config=../k8s/backend.tfvars -backend-config=key=powerlifting-app/coach/terraform.tfstate
terraform -chdir=terraform/coach plan -var-file=terraform.tfvars -out=coach.tfplan
```

Plan files can contain sensitive state. Keep them private and do not commit or
attach them to deployment logs.

Do not reopen the application between these stages. Old images and the new
policies are not a supported mixed deployment.

Verify both the application hostname and Authentik hostname travel through the
intended tunnel/Gateway routes. The OAuth callback is `/oauth2/callback` on the
application host. Discord's OAuth callback belongs to the existing Authentik
source, not Express.

## Preserve identity

Run the pointer migration in dry-run mode first:

```bash
python3 scripts/migrate_identity_pointers.py
```

It considers already verified stored provider identities. An explicit `--apply`
performs conditional writes. Resolve reported ambiguity before cutover; never
merge by email, nickname or display name.

Verify the operator account and representative Athlete, Coach and Handler logins.
A verified Authentik login carrying Discord subject claims establishes the bot's
identity pointer to the same Person. Confirm that Person keys, selected Athlete,
grants, competition scope and authored notes are preserved.

## Live acceptance

Keep the portal in maintenance until all of these pass:

| Request or failure | Required result |
| --- | --- |
| Browser sign-in through Authentik and Discord | Same Person and Athlete data |
| Anonymous public profile and published current Sessions | Existing public reads succeed |
| Private profile or unpublished domain | Denied |
| Forged identity, caller or access-context headers | No impersonation |
| Missing, expired, altered or wrong-scope principal | Denied |
| Unauthorized pod via Service DNS, ClusterIP or Pod IP | Denied before handler execution |
| Authorized workload without effective user grant | Denied |
| Same operation through typed HTTP and MCP | Equivalent permissions |
| Grant revocation or expiry before next request | Next protected request denied |
| Authorizer or permission-store unavailable | Denied |
| Partial, malformed or over-10-MiB inspected JSON | Denied; oversized requests return 413 |
| Large existing imports and bounded video uploads | Work through their intended paths |
| Coach chat, nested tools, continuation and job polling | Preserve Person/Athlete/job ownership |
| Discord chat and management | Only verified linked identity and authorized management |
| Analytics, caches, probes and monitoring | Remain functional |

For direct-access tests, use temporary test pods with unprivileged ServiceAccounts
and test both unenrolled and Ambient-enrolled sources. Do not change an existing
service's identity to perform a test. Confirm successful access also traverses the
expected waypoint and that its authorized-destination decision matches the
Service-scoped ALLOW policy. Direct Pod-IP requests must not bypass that policy.

Observe authorization failures/latency, waypoint and proxy health, and node memory
through existing monitoring. Reopen only after the positive and negative checks
pass together.

## Rollback

Select `master` in the Actions workflow and run it with `apply_terraform=true`,
`backend_only=false` and `frontend_only=false`. This is a full pipeline reapply:
it rebuilds master's six images, publishes/resolves `latest`, restores its AWS
routing configuration, and reapplies `core`, `perms`, `network`, `app` and Coach's
existing separate state. A local branch switch does not start that workflow.

The original core signing/session resources and shared Kubernetes secret retain
their Terraform addresses and values so master can consume them again. New
runtime workloads do not mount that secret or implement old authentication.
Master's same-state reapply removes branch-only app/Coach policies, proxy and
waypoint resources and restores its workload labels, routes and Authentik
provider/source settings. Keep the portal closed until app and Coach complete;
the intermediate mixed deployment is unsupported.

The separate Istio foundation remains installed because master does not manage
its state. Added identity pointers, Authentik user links and externally supplied
signing-key parameters also remain. This restores the master application release,
not a byte-for-byte snapshot of infrastructure and data. Do not remove CNI or
shared Gateway API CRDs as incident recovery.

After the master pipeline succeeds, check browser login, the existing Person's
data, Coach and Discord. Confirm branch policies and waypoint attachments are
gone from restored app/Coach workloads, and confirm their image digests match
the master build. A live feature-to-master round trip has not been performed;
complete that acceptance test during the maintenance window before relying on
the rollback contract. No runtime fallback code exists in this branch.
