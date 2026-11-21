variable "kubernetes_api_cidrs" {
  type    = set(string)
  default = []
}

variable "network_policy_ingress_databases" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_ingress_databases, toset(["assistant-postgres", "litellm-postgres"]))) == 0
    error_message = "Only assistant-postgres and litellm-postgres are managed here."
  }
}

variable "network_policy_egress_databases" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_egress_databases, toset(["assistant-postgres", "litellm-postgres"]))) == 0
    error_message = "Only assistant-postgres and litellm-postgres are managed here."
  }
}

resource "kubectl_manifest" "database_network_policy" {
  for_each = setunion(var.network_policy_ingress_databases, var.network_policy_egress_databases)

  yaml_body = yamlencode({
    apiVersion = "networking.k8s.io/v1"
    kind       = "NetworkPolicy"
    metadata   = { name = "${each.key}-isolation", namespace = var.namespace }
    spec = merge({
      podSelector = { matchLabels = { "cnpg.io/cluster" = each.key } }
      policyTypes = concat(contains(var.network_policy_ingress_databases, each.key) ? ["Ingress"] : [], contains(var.network_policy_egress_databases, each.key) ? ["Egress"] : [])
      }, contains(var.network_policy_ingress_databases, each.key) ? {
      ingress = [
        { from = [{ podSelector = { matchLabels = { app = each.key == "assistant-postgres" ? "pl-assistant" : "litellm" } } }, { podSelector = { matchLabels = { "cnpg.io/cluster" = each.key } } }], ports = [{ protocol = "TCP", port = 5432 }] },
        { from = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "cnpg-system" } }, podSelector = { matchLabels = { "app.kubernetes.io/name" = "cloudnative-pg" } } }], ports = [{ protocol = "TCP", port = 8000 }] },
        { from = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "monitoring" } }, podSelector = { matchLabels = { app = "prometheus" } } }], ports = [{ protocol = "TCP", port = 9187 }] },
        { from = [{ ipBlock = { cidr = "169.254.7.127/32" } }] }
      ]
      } : {}, contains(var.network_policy_egress_databases, each.key) ? {
      egress = concat([
        { to = [{ podSelector = { matchLabels = { "cnpg.io/cluster" = each.key } } }], ports = [{ protocol = "TCP", port = 5432 }, { protocol = "TCP", port = 8000 }] },
        { to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } }, podSelector = { matchLabels = { "k8s-app" = "kube-dns" } } }], ports = [{ protocol = "UDP", port = 53 }, { protocol = "TCP", port = 53 }] }
      ], [for cidr in var.kubernetes_api_cidrs : { to = [{ ipBlock = { cidr = cidr } }], ports = [{ protocol = "TCP", port = 443 }, { protocol = "TCP", port = 6443 }] }])
    } : {})
  })
  lifecycle {
    precondition {
      condition     = length(var.network_policy_egress_databases) == 0 || length(var.kubernetes_api_cidrs) > 0
      error_message = "Set kubernetes_api_cidrs before isolating workloads that call the Kubernetes API."
    }
  }

}
