# ADR 0010 — AWS workload identity and network hardening

Date: 2026-11-19

## Status

Accepted

## Context

Kubernetes workloads currently share the `powerlifting-pods` IAM user's long-lived
access key, delivered through SSM and a Kubernetes Secret. That credential grants
more AWS access than any one workload needs. The cluster is single-node k3s and
Istio Ambient is already the workload network boundary; tightening either
identity or network policy must preserve its existing traffic paths and recovery
options.

## Decision

### AWS identity

Use the cluster's projected Kubernetes service-account tokens with AWS STS
`AssumeRoleWithWebIdentity`. The AWS stack owns the IAM OIDC provider, discovery
and JWKS publication, per-workload roles and policies. The existing k3s issuer
URL is the issuer of record; changing it requires the documented operator
restart and is performed only as an explicit migration step. The public S3
objects are limited to the issuer discovery document and its JWKS. No workload
data is public, and no S3 bucket-wide public-read grant is allowed.

The issuer is hosted at
`https://powerlifting-workload-identity-429310424269-ca-central-1.s3.ca-central-1.amazonaws.com`.
The AWS root inputs are `workload_identity_enabled` and
`workload_identity_jwks`; IAM roles are named `nolift-<service-account>`.

Each role trust policy matches both the exact issuer audience (`sts.amazonaws.com`)
and the exact `system:serviceaccount:<namespace>:<service-account>` subject for
that role. No wildcard namespace or service-account subjects. IAM permissions
are split by workload and restricted to only the required resource ARNs and
actions. Pod identity is not inferred from Kubernetes labels or a caller
supplied role name.

Migration is staged. First publish and verify discovery/JWKS and create the
roles without changing workloads. Then select one canary (`pl-rankings`) with
`aws_workload_identity` and verify STS and its actual S3 access. Move remaining
workloads in small groups, setting the same input independently in app and
Coach. Keep the legacy key valid and mounted during each canary window. Only
after all AWS-using workloads have passed positive and negative checks may the
operator disable and later delete the IAM user's access key, and remove
`/powerlifting/k8s/aws-credentials` from SSM. The agent does not delete AWS
resources. ECR image pulls continue using the existing `ecr-registry` pull
secret and refresher; they do not use application pod identity. Kubernetes API
tokens required by Dapr sidecars and the registry refresher remain mounted and
are not replaced by the AWS projected token.

### Network policy

Harden Ambient incrementally with `pl-rankings` as the first canary. Kubernetes
NetworkPolicy has no built-in observe mode; inspect ztunnel logs and available
CNI telemetry before enforcement, then verify with the canary checks. Ingress
must permit the existing ingress gateway path. Ambient HBONE requires
TCP port 15008 between enrolled workloads and ztunnel/waypoint paths; do not
block it. Retain readiness/liveness probe reachability and the actual health
ports. Keep exact existing external `ServiceEntry` hosts and ports required by
the service; do not replace them with broad wildcards. Roll the canary back
immediately if healthy requests or probes fail, then expand to the portal app
and Coach only after canary success.

Network rollout uses `network_policy_ingress_workloads`,
`network_policy_egress_workloads`, `external_service_entries_enabled`, and
`waypoint_network_policy_enabled`. These default empty/false; developer
environments opt in explicitly, while production supplies reviewed values.
NetworkPolicy has no built-in audit mode, so operators inspect ztunnel logs and
available CNI telemetry before enforcing. The generated workload allow rules
must be reviewed against live ingress and probe paths. Existing ServiceEntry
hosts remain exact; `exportTo` does not isolate Ambient ServiceEntry visibility.

## Consequences

Compromise of one workload yields only that workload's IAM role permissions.
Issuer/JWKS availability becomes a dependency of new STS sessions; existing
credentials remain usable until expiration. During migration, legacy key
compromise risk persists until the operator disables it. Network enforcement
can expose undocumented dependencies, so staged rollout and tested rollback
are required. No user or training data schema changes.

## Rollback

For a failed AWS canary, restore that Deployment to the legacy mounted AWS
credentials and its previous environment/configuration, confirm AWS calls
recover, and leave its role/provider in place for diagnosis. Do not disable the
legacy key until every workload has passed the migration gate. For network
regression, disable enforcement for the affected policy or restore the prior
policy revision, then verify readiness and representative inbound and outbound
calls before proceeding. Detailed operator steps and checks are in
[`docs/runbooks/aws-workload-identity.md`](../runbooks/aws-workload-identity.md).
