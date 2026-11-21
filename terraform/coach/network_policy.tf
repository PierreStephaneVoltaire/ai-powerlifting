variable "network_policy_ingress_workloads" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_ingress_workloads, toset(["pl-coach", "pl-coach-discord"]))) == 0
    error_message = "Only pl-coach and pl-coach-discord are managed here."
  }
}

variable "network_policy_egress_workloads" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_egress_workloads, toset(["pl-coach", "pl-coach-discord"]))) == 0
    error_message = "Only pl-coach and pl-coach-discord are managed here."
  }
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
      ingress = [
        { from = [{ podSelector = { matchLabels = { "gateway.networking.k8s.io/gateway-name" = "nolift-waypoint" } } }], ports = [{ protocol = "TCP", port = 15008 }] },
        { from = [{ ipBlock = { cidr = "169.254.7.127/32" } }] }
      ]
      } : {}, contains(var.network_policy_egress_workloads, each.key) ? {
      egress = concat([
        { to = [{ podSelector = { matchLabels = { "gateway.networking.k8s.io/gateway-name" = "nolift-waypoint" } } }], ports = [{ protocol = "TCP", port = 15008 }] },
        { to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } }, podSelector = { matchLabels = { "k8s-app" = "kube-dns" } } }], ports = [{ protocol = "UDP", port = 53 }, { protocol = "TCP", port = 53 }] }
      ], each.key == "pl-coach" ? [for app in ["pl-valkey", "pl-prompt-cache-mcp"] : { to = [{ podSelector = { matchLabels = { app = app } } }], ports = [{ protocol = "TCP", port = 15008 }] }] : [])
    } : {})
  })
}
