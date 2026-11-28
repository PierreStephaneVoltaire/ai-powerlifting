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
    aws-sts       = { host = "sts.${var.region}.amazonaws.com", callers = setunion(local.aws_workload_accounts, toset(["pl-coach-discord"])) }
    aws-dynamodb  = { host = "dynamodb.${var.region}.amazonaws.com", callers = toset(["pl-analytics", "pl-profile", "pl-program", "pl-sessions", "pl-competition", "pl-glossary", "pl-federation", "pl-goals", "pl-performance", "pl-weight-log", "pl-export", "pl-imports", "pl-lift-profiles", "pl-templates", "pl-videos", "pl-coach-discord"]) }
    aws-ecr       = { host = "api.ecr.${var.region}.amazonaws.com", callers = toset(["ecr-refresher"]) }
    aws-dataset   = { host = "${var.dataset_bucket}.s3.${var.region}.amazonaws.com", callers = toset(["pl-analytics", "pl-analytics-ai", "pl-analytics-export", "pl-rankings", "pl-assistant"]) }
    aws-videos    = { host = "powerlifting-session-videos.s3.${var.region}.amazonaws.com", callers = toset(["powerlifting-app-backend", "pl-profile", "pl-videos"]) }
    aws-reference = { host = "${local.reference_bucket}.s3.${var.region}.amazonaws.com", callers = toset(["pl-assistant"]) }
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
