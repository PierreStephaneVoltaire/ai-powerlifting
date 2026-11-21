# ADR 0010 — AWS workload identity and network hardening

Date: 2026-11-19

## Status

Accepted

## Decision

### AWS identity

Every AWS-using workload uses a projected Kubernetes service-account token to
assume its dedicated IAM role through AWS STS. There is no shared runtime AWS
key, credential Secret, or workload selection flag. Each role trust
is limited to the exact namespace/service-account subject and
`sts.amazonaws.com` audience. Permissions are scoped to the workload's required
AWS resources and actions.

The deployment pipeline reads public signing keys from the k3s API, publishes
the OIDC discovery document and JWKS through AWS Terraform, and configures the
issuer through the cluster's system-upgrade controller. After k3s is ready, the
pipeline deploys the App and Coach states and checks STS trust. The API server
retains its existing Kubernetes token audiences.

ECR image pulls continue through the registry pull secret/refresher. Kubernetes
API tokens required by the refresher and Dapr remain independent of AWS
projected tokens.

### Network policy

Network isolation is a separate, independently opt-in rollout beginning with
`pl-rankings`. Workload ingress/egress, database ingress/egress, external
ServiceEntries, and waypoint policy remain independently configurable and
empty/false by default. Exact external hosts and caller identities are
preserved. Operators inspect available ztunnel/CNI telemetry before
enforcement; Kubernetes NetworkPolicy has no built-in observe mode. Policies
preserve Ambient HBONE TCP 15008, health probes, DNS, Dapr, waypoint, and
Kubernetes API paths where required.

## Consequences

Compromise of a workload grants only its role's AWS permissions. New STS
sessions depend on issuer/JWKS availability; SDKs refresh short-lived role
credentials using the projected token. Network enforcement can expose
undocumented paths, so its independent canary and rollback remain necessary.

AWS workload identity is the only supported runtime credential path. Network
regressions are handled by reverting only the affected opt-in network policy.
