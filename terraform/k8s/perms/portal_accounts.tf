locals {
  portal_service_accounts = toset(concat(
    ["powerlifting-app-backend", "powerlifting-app-frontend", "oauth2-proxy", "pl-analytics", "pl-analytics-ai", "pl-analytics-export", "pl-valkey", "pl-prompt-cache", "pl-prompt-cache-mcp", "cloudflared"],
    [for name in ["budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "pl-${name}"]
  ))
}

resource "kubernetes_service_account_v1" "portal" {
  for_each = local.portal_service_accounts

  metadata {
    name      = each.key
    namespace = var.namespace
  }
  automount_service_account_token = false
}
