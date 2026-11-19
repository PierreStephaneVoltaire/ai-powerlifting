# AWS workload identity and network hardening

Use this runbook for the projected service-account-token migration in ADR 0010.
Terraform publishes the issuer at
`https://powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com`.
Its two public objects are `/.well-known/openid-configuration` and
`/openid/v1/jwks`. Role names are `nolift-<service-account>`. Confirm the
namespace from applied Terraform; it must match the token subject and trust
policy exactly.

```bash
export AWS_REGION=ca-central-1
export AWS_ACCOUNT_ID=429310424269
export AWS_OIDC_ISSUER='https://powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com'
export AWS_OIDC_BUCKET='powerlifting-workload-identity-429310424269-ca-central-1'
export AWS_OIDC_ROLE='arn:aws:iam::429310424269:role/nolift-pl-rankings'
export K8S_NAMESPACE='powerlifting'
export K8S_SERVICE_ACCOUNT='pl-rankings'
```

Do not apply IAM or bucket changes until the plan shows only the intended
identity resources and policy changes. Never run a broad Terraform apply or
destroy for this procedure. The AWS root stack is applied by CI; Kubernetes
stacks are applied by the in-cluster runner. Coach remains its own local state.

## 1. Confirm current state

Read the live state before making changes:

```bash
kubectl -n "$K8S_NAMESPACE" get deploy pl-rankings -o yaml
kubectl -n "$K8S_NAMESPACE" get sa pl-rankings -o yaml
kubectl -n "$K8S_NAMESPACE" get secret pl-aws-credentials
aws iam list-access-keys --user-name powerlifting-pods
aws ssm get-parameter --name /powerlifting/k8s/aws-credentials --query Parameter.Version --output text
```

Record the current Deployment image, pod template, AWS credential mounts,
readiness status, and SSM parameter version. Do not retrieve or print the
decrypted SSM value. Check the IAM user's current attached and inline policies.
Keep its active key available as rollback until the final retirement gate.

## 2. Prepare the public issuer before switching k3s

Read the live issuer and public verification keys from the API server. Save the
current issuer for legacy acceptance during transition:

```bash
export LEGACY_ISSUER="$(kubectl get --raw /.well-known/openid-configuration | jq -r .issuer)"
JWKS_FILE="$(mktemp)"
chmod 600 "$JWKS_FILE"
kubectl get --raw /openid/v1/jwks > "$JWKS_FILE"
jq -e '(.keys | length > 0) and all(.keys[]; has("n") and has("e") and (has("d") | not) and (has("p") | not) and (has("q") | not))' "$JWKS_FILE"
```

If discovery is not served at that API path, inspect live k3s API-server args
and its configured issuer discovery before continuing. The JWKS must contain
public keys only. Never print or publish a private signing key.

Before the k3s restart, apply the scoped
`terraform/ci-access/workload_identity.tf` state, then set GitHub inputs
`WORKLOAD_IDENTITY_ENABLED=true` and `WORKLOAD_IDENTITY_JWKS` to the public-only
JWKS. Apply the AWS root stack so discovery/JWKS, the IAM provider, exact roles,
and policies exist before k3s issues tokens for the public issuer. The
discovery `issuer` is the S3 URL above, and the JWKS must match the API server
key set.

Verify the public objects contain only the issuer metadata and signing keys:

```bash
curl --fail --silent --show-error "$AWS_OIDC_ISSUER/.well-known/openid-configuration" | jq .
curl --fail --silent --show-error "$AWS_OIDC_ISSUER/openid/v1/jwks" | jq .
aws s3api get-public-access-block --bucket "$AWS_OIDC_BUCKET"
aws s3api get-bucket-policy-status --bucket "$AWS_OIDC_BUCKET"
aws s3api get-bucket-policy --bucket "$AWS_OIDC_BUCKET" | jq .
```

The discovery document's `issuer` must equal `AWS_OIDC_ISSUER`, its `jwks_uri`
must resolve to the published JWKS, and the JWKS must contain the current
verification key. Anonymous requests for these two documents must succeed.
Anonymous `ListBucket`, `GetObject` for an unrelated key, and access to any
application data bucket must fail. The bucket policy must grant public
`GetObject` only for those exact two object ARNs; bucket ACLs remain blocked.
Confirm the provider's thumbprint and audience match the live issuer and
`sts.amazonaws.com`.

## 3. Switch k3s token issuance while retaining legacy acceptance

Proceed only after AWS discovery, provider, roles, and policies are live. Plan a
maintenance window and retain local node access. Put the public issuer first so
newly requested tokens use it; keep the former issuer second so existing
tokens remain accepted. Preserve other server arguments:

```yaml
kube-apiserver-arg:
  - service-account-issuer=https://powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com
  - service-account-issuer=<value-of-LEGACY_ISSUER>
```

Restart k3s and wait for the API server and workloads to recover. Confirm a new
TokenRequest uses the public issuer and `sts.amazonaws.com` audience without
printing the token. Confirm Kubernetes API access remains healthy for the Dapr
workflows and the registry refresher's `ecr-registry` Secret read/patch cycle.
These checks verify Kubernetes API access separately from AWS role trust.

To exercise the registry refresher's Kubernetes API token now, manually run its
existing CronJob and wait for its Secret patch to succeed:

```bash
REGISTRY_JOB="ecr-token-refresher-issuer-check-$(date +%s)"
kubectl -n "$K8S_NAMESPACE" create job --from=cronjob/ecr-token-refresher "$REGISTRY_JOB"
kubectl -n "$K8S_NAMESPACE" wait --for=condition=complete "job/$REGISTRY_JOB" --timeout=5m
kubectl -n "$K8S_NAMESPACE" logs "job/$REGISTRY_JOB"
```

Also start or resume one known Dapr workflow and confirm its activity reaches
completion. The token verifier below independently checks live AWS OIDC trust.

Review each role trust policy before rollout. It must contain both:

- `aud = sts.amazonaws.com`
- `sub = system:serviceaccount:<namespace>:<exact-service-account>`

Run positive and negative `AssumeRoleWithWebIdentity` checks using TokenRequest
tokens. A wrong service account or cross-role token must receive an AWS
authorization denial. A wrong-audience token counts as a successful negative
check only when STS reports an audience mismatch; issuer key retrieval and
transport errors are failed checks.

The repository verifier uses the runner's boto3 dependency for STS; it does not
require AWS CLI. It performs TokenRequest and STS checks without printing token
or credential data, verifies the assumed role ARN, and classifies issuer key
retrieval and transport errors as failures:

```bash
python3 scripts/verify_workload_identity.py \
  --namespace "$K8S_NAMESPACE" \
  --region "$AWS_REGION" \
  --account-id "$AWS_ACCOUNT_ID" \
  --service-account pl-rankings \
  --role-arn "$AWS_OIDC_ROLE" \
  --unrelated-service-account default
```

If the unrelated service account is not `default` in the target cluster, pass
the name of a known existing service account that is not trusted by this role.
To check another migrated role and service account, also pass both
`--other-role-arn` and `--other-service-account`; the script checks that pair
works and that the canary token cannot assume the other role. This verifier
does not mutate cluster/AWS resources and must be run only after the target
roles and JWKS have been applied.

For key rotation, publish a JWKS containing both the current and replacement
public keys before k3s starts signing with the replacement. Apply the AWS root
stack to republish the JWKS, verify both keys are served, then rotate the
signing key and verify fresh STS assumptions. Keep the old public key published
until all tokens signed with it have expired; only then remove it from JWKS.

## 4. Migrate `pl-rankings` canary

Keep `workload_identity_namespace` matched to the live namespace. Confirm
the target role has only the dataset S3 actions and resource prefix the service
needs. Confirm it has no DynamoDB, ECR, IAM, or unrelated S3 permissions.
Then set `aws_workload_identity = ["pl-rankings"]` in `K8S_TFVARS` and apply
the app-stack change through the normal in-cluster workflow. This set contains
service-account names; leave it empty for workloads not migrated yet.

Check the projected token exists at the configured mount without printing its
contents. The verifier confirms live STS identity and exact role. Exercise the
rankings dataset list/read through a real request and confirm readiness. Keep a
long-lived pod serving traffic for at least 75 minutes so its AWS SDK must
refresh web-identity credentials after the default one-hour STS session and
continue without a pod restart. Keep the legacy key available during this
canary period.

Do not run write/delete smoke tests against live dataset data. Rankings needs
`s3:PutObject` to refresh its cached dataset, so use IAM policy simulation for
positive Get/Put and negative Delete/unrelated-object checks, then use a live
dataset read for end-to-end validation:

```bash
aws iam simulate-principal-policy --policy-source-arn "$AWS_OIDC_ROLE" \
  --action-names s3:GetObject s3:PutObject \
  --resource-arns arn:aws:s3:::powerlifting-data-2b0f699b/datasets/openpowerlifting-example.parquet \
  --query 'EvaluationResults[].EvalDecision' --output text
aws iam simulate-principal-policy --policy-source-arn "$AWS_OIDC_ROLE" \
  --action-names s3:DeleteObject s3:GetObject \
  --resource-arns arn:aws:s3:::powerlifting-data-2b0f699b/unrelated-object \
  --query 'EvaluationResults[].EvalDecision' --output text
```

The first result should be `allowed` for both actions. The second should be
`implicitDeny` for both actions. Simulation verifies the IAM policy without
mutating data; the real request verifies workload credentials and network path.

Observe the Deployment and application logs through at least a normal service
use interval:

```bash
kubectl -n "$K8S_NAMESPACE" rollout status deploy/pl-rankings
kubectl -n "$K8S_NAMESPACE" get pods -l app=pl-rankings -o wide
kubectl -n "$K8S_NAMESPACE" logs deploy/pl-rankings --since=30m
kubectl -n "$K8S_NAMESPACE" get events --sort-by=.lastTimestamp
```

Verify readiness remains green, the `pl-rankings` Service is reachable through
the waypoint from each existing caller, and an unauthorized caller is denied.
Inspect CloudTrail for `AssumeRoleWithWebIdentity` by the exact provider/role
and check for unexpected AWS actions. Do not proceed if there are unexplained
denials or permissions.

## 5. Expand in groups

Migrate workloads in small, operationally separable groups, applying AWS role
trust/policy before the corresponding Kubernetes rollout. For every workload,
repeat the positive checks (correct role, required operation, healthy probes)
and negative checks (wrong service account, wrong audience, unrelated resource
and actions outside the policy). Coach uses the separate `terraform/coach/`
state and is migrated only after the portal app canary and groups are stable.

Retain Kubernetes API tokens required by Dapr sidecars and the registry
refresher. Retain the ECR `ecr-registry` image pull secret and its refresh
service account. Verify Dapr workflow activity and registry secret refresh
independently; neither is proof of the pod's AWS role.

## 6. Network canary and rollout

Use `pl-rankings` as the first policy canary. NetworkPolicy has no built-in
observe mode. Before enforcing, inspect ztunnel logs and available CNI network
telemetry. Validate the live kube-dns path, Dapr peers, waypoint/ztunnel source
and destination addresses, and the ingress probe behavior; CNI NAT can affect
which source selectors match. Preserve HBONE TCP 15008 and the configured
health probe paths. Check external dependencies against exact ServiceEntry
hosts; never replace them with wildcards.

Before creating ServiceEntry resources, enable and verify
`namespace_service_entry_visibility_enabled` in the mesh state. Then enable
`external_service_entries_enabled` for the predefined exact AWS, Authentik,
Discord, OpenRouter, OpenAI, dataset, video, and reference endpoints. Other
configured hosts must be explicit exact entries with caller service accounts.
Ambient ServiceEntry visibility is not namespace-scoped by `exportTo`.

Set `network_policy_ingress_workloads = ["pl-rankings"]` and
`network_policy_egress_workloads = ["pl-rankings"]` independently for the app
canary. Core database policy selectors are
`network_policy_ingress_databases` and `network_policy_egress_databases`, using
`cnpg.io/cluster` labels. Set `kubernetes_api_cidrs` before isolating databases
or the registry refresher; Assistant also needs Kubernetes API access. Apply
only the relevant state and inspect its plan. Before tightening workload
egress, verify external and backhaul paths, then enable
`waypoint_network_policy_enabled` so the waypoint's DNS, Istio control-plane,
mesh, and external TLS paths have their intended rules before workloads rely on
it for external traffic. Keep external hosts exact and their ServiceEntry
caller policies scoped.

Run the network canary against an existing curl-capable canary pod, an
authorized caller pod, and an unauthorized caller pod. Choose an operator-
verified positive HTTPS URL/status, an unknown HTTPS hostname, a known-reachable
public IP, and the canary health URL:

```bash
python3 scripts/verify_network_canary.py \
  --namespace "$K8S_NAMESPACE" \
  --canary-pod "$CANARY_POD" \
  --authorized-pod "$AUTHORIZED_POD" \
  --unauthorized-pod "$UNAUTHORIZED_POD" \
  --allowed-url "$KNOWN_ALLOWED_HTTPS_URL" \
  --allowed-status "$KNOWN_ALLOWED_HTTP_STATUS" \
  --unknown-url "$UNKNOWN_HTTPS_URL" \
  --public-ip "$KNOWN_REACHABLE_PUBLIC_IP" \
  --ingress-url "$CANARY_HEALTH_URL" \
  --ingress-status 200
```

The script checks allowed external egress, unknown-host and raw-IP rejection,
SNI to an unrelated IP, authorized ingress, and unauthorized ingress. A `403`
from the application is not sufficient evidence of a mesh deny; inspect
waypoint/ztunnel logs separately, and do not treat DNS or command-execution
errors as a policy deny. Also check both `pl-rankings` replicas and probes,
known caller requests, ingress through the existing gateway, and TCP 15008.
After canary success, add other exact app labels; migrate portal, databases,
and Coach separately. All network inputs default empty/false, so developer
environments opt in explicitly and production inputs must explicitly carry
reviewed sets.

## Rollback

For a workload identity failure, roll back only the affected Deployment to its
last known pod template with the legacy AWS credentials mounted. For example,
use the normal protected-branch deployment workflow with the previous image
and configuration. Confirm new pods assume no projected role and that the
original required AWS call succeeds. Keep the role and provider resources for
diagnosis. Do not remove the legacy SSM parameter or disable the IAM access key.

If reverting the k3s issuer migration, first return workloads to the legacy AWS
credential configuration while leaving public issuer roles available. Then put
the legacy issuer first and the public S3 issuer second in k3s API-server args,
restart k3s, and verify both old and new projected tokens are still accepted.
Keep both issuers in the accepted list until all tokens from the secondary
issuer have expired. Do not remove the public provider/JWKS during rollback.

For a network regression, restore the previous policy revision or disable
enforcement for the affected canary using its owning Kubernetes Terraform
stack, then verify probes, gateway ingress, waypoint traffic, DNS, exact
external hosts, and Ambient port 15008. Avoid broad policy deletion; preserve
the live IF agent API and other workloads.

If any rollback requires AWS resource removal, provide the exact reviewed
operator command and let the operator perform it. This runbook never authorizes
the agent to delete AWS resources.

## 7. Retire the shared key

Set `aws_workload_identity` in both app and Coach inputs to their exact migrated
service-account sets. Keep `retain_shared_aws_credentials = true` in core until
both stacks are migrated and validated. Only then set it false to remove the
shared credential Secret and SSM lookup. Only after every AWS-using workload
has passed the positive and negative checks,
has run successfully without fallback, and CloudTrail shows expected
workload-role usage:

1. Roll out every workload without the legacy key mount and confirm it remains
   healthy through at least one AWS credential refresh interval.
2. Have the operator set `retain_shared_aws_credentials = false` and apply the
   core state to remove the Kubernetes Secret and SSM lookup. Keep the SSM
   parameter and active access key during the observation window.
3. Have the operator identify and disable the key without printing any secret:

   ```bash
   PODS_ACCESS_KEY_ID="$(aws iam list-access-keys --user-name powerlifting-pods --query 'AccessKeyMetadata[?Status==`Active`].AccessKeyId | [0]' --output text)"
   aws iam update-access-key --user-name powerlifting-pods --access-key-id "$PODS_ACCESS_KEY_ID" --status Inactive
   ```

   Keep it disabled through the agreed observation window. If rollback is
   needed, the operator can reactivate this same key.
4. After the window passes, have the operator delete the disabled key and SSM
   parameter:

   ```bash
   aws iam delete-access-key --user-name powerlifting-pods --access-key-id "$PODS_ACCESS_KEY_ID"
   aws ssm delete-parameter --name /powerlifting/k8s/aws-credentials
   ```

5. Confirm the IAM user has no remaining active keys or workload policy use.

Disabling/deleting the key and removing SSM data are operator actions. Never
delete the IAM user or any AWS resource as part of this migration.
