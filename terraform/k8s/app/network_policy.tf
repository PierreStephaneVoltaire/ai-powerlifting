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
  network_valid_workloads   = toset(concat(keys(local.mesh_callers), keys(local.cache_callers), ["powerlifting-app-backend", "powerlifting-app-frontend", "oauth2-proxy", "reference-litellm", "litellm-keys", "ecr-token-refresher"]))
  network_pod_names         = { "pl-litellm-keys" = "litellm-keys", "ecr-refresher" = "ecr-token-refresher" }
  network_waypoint_selector = { "gateway.networking.k8s.io/gateway-name" = "nolift-waypoint" }
  network_edge_selector     = { "gateway.networking.k8s.io/gateway-name" = "edge" }
  network_waypoint_callers  = toset(concat(flatten(values(local.mesh_callers)), flatten([for entry in values(local.all_external_service_entries) : tolist(entry.callers)]), ["pl-assistant", "pl-coach", "pl-coach-discord"]))
  network_cache_callers     = { for target, callers in local.cache_callers : target => [for caller in callers : lookup(local.network_pod_names, caller, caller)] }
}

resource "kubectl_manifest" "workload_network_policy" {
  for_each = setunion(var.network_policy_ingress_workloads, var.network_policy_egress_workloads)

  yaml_body = yamlencode({
    apiVersion = "networking.k8s.io/v1"
    kind       = "NetworkPolicy"
    metadata   = { name = "${each.key}-isolation", namespace = var.namespace }
    spec = merge({
      podSelector = { matchLabels = { app = each.key } }
      policyTypes = concat(contains(var.network_policy_ingress_workloads, each.key) ? ["Ingress"] : [], contains(var.network_policy_egress_workloads, each.key) ? ["Egress"] : [])
      }, contains(var.network_policy_ingress_workloads, each.key) ? {
      ingress = concat(
        contains(concat(keys(local.mesh_callers), ["pl-coach", "pl-coach-discord", "reference-litellm"]), each.key) ? [{ from = [{ podSelector = { matchLabels = local.network_waypoint_selector } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        [for caller in lookup(local.network_cache_callers, each.key, []) : { from = [{ podSelector = { matchLabels = { app = caller } } }], ports = [{ protocol = "TCP", port = 15008 }] }],
        each.key == "powerlifting-app-backend" ? [{ from = [{ podSelector = { matchLabels = { app = "oauth2-proxy" } } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        contains(["powerlifting-app-frontend", "oauth2-proxy", "litellm"], each.key) ? [{ from = [{ podSelector = { matchLabels = local.network_edge_selector } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        each.key == "pl-assistant" ? [{ from = [{ podSelector = { matchLabels = { app = "pl-assistant" } } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        [{ from = [{ ipBlock = { cidr = "169.254.7.127/32" } }] }]
      )
      } : {}, contains(var.network_policy_egress_workloads, each.key) ? {
      egress = concat(
        contains([for caller in local.network_waypoint_callers : lookup(local.network_pod_names, caller, caller)], each.key) ? [{ to = [{ podSelector = { matchLabels = local.network_waypoint_selector } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        flatten([for target, callers in local.network_cache_callers : contains(callers, each.key) ? [{ to = [{ podSelector = { matchLabels = { app = target } } }], ports = [{ protocol = "TCP", port = 15008 }] }] : []]),
        each.key == "oauth2-proxy" ? [{ to = [{ podSelector = { matchLabels = { app = "powerlifting-app-backend" } } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [],
        contains(["pl-assistant", "litellm"], each.key) ? [{ to = [{ podSelector = { matchLabels = { "cnpg.io/cluster" = each.key == "pl-assistant" ? "assistant-postgres" : "litellm-postgres" } } }], ports = [{ protocol = "TCP", port = 5432 }] }] : [],
        each.key == "pl-assistant" ? concat(
          [{ to = [{ podSelector = { matchLabels = { app = "pl-assistant" } } }], ports = [{ protocol = "TCP", port = 15008 }] }],
          [for service, port in { "dapr-sentry" = 50001, "dapr-placement-server" = 50005, "dapr-scheduler-server" = 50006, "dapr-operator" = 6500 } : { to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "dapr-system" } }, podSelector = { matchLabels = { app = service } } }], ports = [{ protocol = "TCP", port = port }] }]
        ) : [],
        [{ to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } }, podSelector = { matchLabels = { "k8s-app" = "kube-dns" } } }], ports = [{ protocol = "UDP", port = 53 }, { protocol = "TCP", port = 53 }] }],
        contains(["ecr-token-refresher", "pl-assistant"], each.key) ? [for cidr in var.kubernetes_api_cidrs : { to = [{ ipBlock = { cidr = cidr } }], ports = [{ protocol = "TCP", port = 443 }, { protocol = "TCP", port = 6443 }] }] : []
      )
    } : {})
  })
  lifecycle {
    precondition {
      condition     = length(setsubtract(setunion(var.network_policy_ingress_workloads, var.network_policy_egress_workloads), local.network_valid_workloads)) == 0
      error_message = "Unknown app network policy selector."
    }
    precondition {
      condition     = length(var.network_policy_egress_workloads) == 0 || var.external_service_entries_enabled
      error_message = "Stage and verify the external ServiceEntries before enabling workload egress isolation."
    }
    precondition {
      condition     = length(setintersection(var.network_policy_egress_workloads, toset(["ecr-token-refresher", "pl-assistant"]))) == 0 || length(var.kubernetes_api_cidrs) > 0
      error_message = "Set kubernetes_api_cidrs before isolating workloads that call the Kubernetes API."
    }
  }

}
