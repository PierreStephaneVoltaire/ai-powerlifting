variable "network_policy_ingress_workloads" {
  type    = set(string)
  default = []
}

variable "network_policy_egress_workloads" {
  type    = set(string)
  default = []
}

variable "kubernetes_api_cidrs" {
  type    = set(string)
  default = []
  validation {
    condition     = alltrue([for cidr in var.kubernetes_api_cidrs : can(cidrhost(cidr, 0))])
    error_message = "kubernetes_api_cidrs must contain valid CIDRs."
  }
}

locals {
  isolation_policies = [for doc in split("\n---\n", file("${path.module}/../../../deploy/argocd/app/network-policy.yaml")) : yamldecode(doc)]
  network_valid_workloads = toset([for policy in local.isolation_policies : policy.metadata.annotations["nolift.io/isolation"]
    if can(policy.metadata.annotations["nolift.io/isolation"])
  ])
  service_policies = [for doc in split("\n---\n", file("${path.module}/../../../deploy/argocd/app/mesh.yaml")) : yamldecode(doc)]
  mesh_principals = flatten([for policy in local.service_policies : [
    for rule in policy.spec.rules : [for from in try(rule.from, []) : try(from.source.principals, [])]
  ] if endswith(policy.metadata.name, "-allowed-callers")])
  network_pod_names = { "pl-litellm-keys" = "litellm-keys", "ecr-refresher" = "ecr-token-refresher" }
  network_waypoint_callers = toset(concat(
    [for principal in local.mesh_principals : trimprefix(principal, "cluster.local/ns/${var.namespace}/sa/")],
    flatten([for entry in values(local.all_external_service_entries) : tolist(entry.callers)]),
    ["pl-assistant", "pl-coach", "pl-coach-discord"],
  ))
}
