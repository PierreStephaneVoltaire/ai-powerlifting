variable "external_service_entries_enabled" {
  type    = bool
  default = false
}

variable "external_service_entries" {
  type = map(object({
    host    = string
    callers = set(string)
  }))
  default = {}

  validation {
    condition     = alltrue([for entry in values(var.external_service_entries) : can(regex("^[a-z0-9]([a-z0-9.-]*[a-z0-9])?$", entry.host)) && !can(cidrhost("${entry.host}/32", 0)) && length(entry.callers) > 0])
    error_message = "External hosts must be exact DNS names and have at least one caller."
  }
}

variable "waypoint_network_policy_enabled" {
  type    = bool
  default = false
}

locals {
  required_external_service_entries = {
    authentik     = { host = var.auth_domain, callers = toset(["oauth2-proxy", "litellm"]) }
    discord-api   = { host = "discord.com", callers = toset(["pl-profile", "pl-coach-discord"]) }
    discord-cdn   = { host = "cdn.discordapp.com", callers = toset(["pl-profile", "pl-coach-discord"]) }
    openrouter    = { host = "openrouter.ai", callers = toset(["litellm", "reference-litellm"]) }
    openai-api    = { host = "api.openai.com", callers = toset(concat(["pl-prompt-cache-api"], anytrue([for provider in values(var.litellm_providers) : provider.type == "openai" && provider.base_url == null]) ? ["litellm"] : [])) }
    aws-sts       = { host = "sts.${var.region}.amazonaws.com", callers = setunion(setsubtract(local.aws_workload_accounts, local.credentialless_accounts), toset(["pl-coach", "pl-coach-discord"])) }
    aws-dynamodb  = { host = "dynamodb.${var.region}.amazonaws.com", callers = toset(["pl-analytics", "pl-profile", "pl-program", "pl-sessions", "pl-competition", "pl-glossary", "pl-federation", "pl-goals", "pl-performance", "pl-weight-log", "pl-export", "pl-imports", "pl-lift-profiles", "pl-templates", "pl-videos", "pl-coach-discord"]) }
    aws-ecr       = { host = "api.ecr.${var.region}.amazonaws.com", callers = toset(["ecr-refresher"]) }
    aws-dataset   = { host = "${var.dataset_bucket}.s3.${var.region}.amazonaws.com", callers = toset(["pl-analytics", "pl-analytics-ai", "pl-analytics-export", "pl-rankings", "pl-coach"]) }
    aws-videos    = { host = "powerlifting-session-videos.s3.${var.region}.amazonaws.com", callers = toset(["powerlifting-app-backend", "pl-profile", "pl-videos"]) }
    aws-reference = { host = "powerlifting-reference-documents-429310424269-ca-central-1.s3.${var.region}.amazonaws.com", callers = toset(["pl-assistant"]) }
  }
  all_external_service_entries = merge(var.external_service_entries, local.required_external_service_entries)
}

resource "kubectl_manifest" "external_service" {
  for_each = var.external_service_entries_enabled ? local.all_external_service_entries : {}

  yaml_body = yamlencode({
    apiVersion = "networking.istio.io/v1"
    kind       = "ServiceEntry"
    metadata   = { name = each.key, namespace = var.namespace, labels = { "istio.io/use-waypoint" = "nolift-waypoint" } }
    spec = {
      hosts      = [each.value.host]
      location   = "MESH_EXTERNAL"
      resolution = "DNS"
      ports      = [{ number = 443, name = "tls", protocol = "TLS" }]
      exportTo   = ["."]
    }
  })
}

resource "kubectl_manifest" "external_callers" {
  for_each = var.external_service_entries_enabled ? local.all_external_service_entries : {}

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-external-callers", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "networking.istio.io", kind = "ServiceEntry", name = each.key }]
      action     = "ALLOW"
      rules      = [{ from = [{ source = { principals = [for caller in each.value.callers : "cluster.local/ns/${var.namespace}/sa/${caller}"] } }] }]
    }
  })
  depends_on = [kubectl_manifest.external_service]
}

resource "kubectl_manifest" "waypoint_network_policy" {
  count = var.waypoint_network_policy_enabled ? 1 : 0

  lifecycle {
    precondition {
      condition     = var.external_service_entries_enabled
      error_message = "Stage and verify external ServiceEntries before isolating the waypoint."
    }
  }

  yaml_body = yamlencode({
    apiVersion = "networking.k8s.io/v1"
    kind       = "NetworkPolicy"
    metadata   = { name = "nolift-waypoint-isolation", namespace = var.namespace }
    spec = {
      podSelector = { matchLabels = { "gateway.networking.k8s.io/gateway-name" = "nolift-waypoint" } }
      policyTypes = ["Ingress", "Egress"]
      ingress = [
        { from = [for caller in local.network_waypoint_callers : { podSelector = { matchLabels = { app = lookup(local.network_pod_names, caller, caller) } } }], ports = [{ protocol = "TCP", port = 15008 }] },
        { from = [{ ipBlock = { cidr = "169.254.7.127/32" } }] }
      ]
      egress = [
        { to = [for target in concat(keys(local.mesh_callers), ["pl-coach", "pl-coach-discord", "reference-litellm"]) : { podSelector = { matchLabels = { app = target } } }], ports = [{ protocol = "TCP", port = 15008 }] },
        { to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "istio-system" } }, podSelector = { matchLabels = { app = "istiod" } } }], ports = [{ protocol = "TCP", port = 15012 }] },
        { to = [{ namespaceSelector = { matchLabels = { "kubernetes.io/metadata.name" = "kube-system" } }, podSelector = { matchLabels = { "k8s-app" = "kube-dns" } } }], ports = [{ protocol = "UDP", port = 53 }, { protocol = "TCP", port = 53 }] },
        { to = [{ ipBlock = { cidr = "0.0.0.0/0", except = ["0.0.0.0/8", "10.0.0.0/8", "100.64.0.0/10", "127.0.0.0/8", "169.254.0.0/16", "172.16.0.0/12", "192.168.0.0/16", "224.0.0.0/4", "240.0.0.0/4"] } }], ports = [{ protocol = "TCP", port = 443 }] }
      ]
    }
  })
}
