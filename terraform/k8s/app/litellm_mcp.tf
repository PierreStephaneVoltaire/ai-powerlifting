variable "litellm_mcp_servers" {
  type = map(object({
    url           = string
    extra_headers = optional(list(string), ["authorization"])
  }))
  default = {}
}

locals {
  litellm_mcp_domains = ["sessions", "program", "competition", "profile", "glossary", "templates", "goals", "performance", "lift-profiles", "weight-log", "federation", "calculations"]
  litellm_mcp_registry = merge(
    {
      for domain in local.litellm_mcp_domains : replace(domain, "-", "_") => {
        url           = "http://pl-${domain}.${var.namespace}.svc.cluster.local:8000/mcp"
        extra_headers = ["authorization"]
      }
    },
    var.litellm_mcp_servers,
  )

  litellm_mcp_servers = {
    for alias, server in local.litellm_mcp_registry : alias => {
      url           = server.url
      transport     = "http"
      auth_type     = "none"
      extra_headers = server.extra_headers
    }
  }

  litellm_virtual_key_consumers = {
    assistant = {
      models      = ["pl-coordinator", "pl-responder-fast", "pl-embed", "pl-light", "pl-strong", "pl-web", "pl-analysis", "pl-standard", "pl-documents", "pl-background"]
      mcp_servers = sort(keys(local.litellm_mcp_registry))
    }
  }

  litellm_virtual_key_registration = sha256(jsonencode({
    consumers = local.litellm_virtual_key_consumers
    keys      = { for consumer, key in random_password.litellm_virtual_key : consumer => key.result }
    script    = local.litellm_key_registration_script
  }))

  litellm_key_registration_script = <<-EOT
    set -eu
    base=http://litellm.${var.namespace}.svc.cluster.local:4000
    attempt=0
    until [ "$(curl -s -o /dev/null -w '%%{http_code}' "$base/health/liveliness")" = "200" ]; do
      attempt=$((attempt + 1))
      if [ "$attempt" -ge 120 ]; then echo "litellm not reachable" >&2; exit 1; fi
      sleep 5
    done
    register() {
      consumer="$1"; key="$2"; models="$3"; servers="$4"
      status=$(curl -s -o /dev/null -w '%%{http_code}' -G "$base/key/info" --data-urlencode "key=$key" -H "Authorization: Bearer $LITELLM_MASTER_KEY")
      if [ "$status" = "200" ]; then
        body=$(jq -n --arg key "$key" --arg alias "$consumer" --argjson models "$models" --argjson servers "$servers" '{key: $key, key_alias: $alias, models: $models, metadata: {consumer: $alias}, object_permission: {mcp_servers: $servers}}')
        status=$(curl -s -o /tmp/response -w '%%{http_code}' "$base/key/update" -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" -d "$body")
        if [ "$status" = "200" ]; then echo "$consumer key updated"; return 0; fi
        cat /tmp/response >&2
        return 1
      fi
      body=$(jq -n --arg key "$key" --arg alias "$consumer" --argjson models "$models" --argjson servers "$servers" '{key: $key, key_alias: $alias, models: $models, metadata: {consumer: $alias}, object_permission: {mcp_servers: $servers}}')
      status=$(curl -s -o /tmp/response -w '%%{http_code}' "$base/key/generate" -H "Authorization: Bearer $LITELLM_MASTER_KEY" -H "Content-Type: application/json" -d "$body")
      if [ "$status" = "200" ]; then echo "$consumer key registered"; return 0; fi
      if grep -qi "already exists\|already in use\|duplicate" /tmp/response; then echo "$consumer key already exists"; return 0; fi
      cat /tmp/response >&2
      return 1
    }
    ${join("\n    ", [for consumer, access in local.litellm_virtual_key_consumers : "register ${consumer} \"$KEY_${upper(consumer)}\" '${jsonencode(access.models)}' '${jsonencode(access.mcp_servers)}'"])}
  EOT
}

resource "random_password" "litellm_virtual_key" {
  for_each = local.litellm_virtual_key_consumers

  length  = 48
  special = false
}

resource "kubernetes_secret_v1" "litellm_virtual_key" {
  for_each = local.litellm_virtual_key_consumers

  metadata {
    name      = "litellm-virtual-key-${each.key}"
    namespace = var.namespace
  }

  data = {
    LITELLM_API_KEY = "sk-${random_password.litellm_virtual_key[each.key].result}"
  }
}

resource "kubernetes_job_v1" "litellm_keys" {
  metadata {
    name      = "litellm-keys-${substr(local.litellm_virtual_key_registration, 0, 10)}"
    namespace = var.namespace
  }

  spec {
    backoff_limit = 6

    template {
      metadata {
        labels = { app = "litellm-keys", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "pl-litellm-keys"
        automount_service_account_token = false
        enable_service_links            = false
        restart_policy                  = "OnFailure"

        container {
          name    = "register"
          image   = "public.ecr.aws/aws-cli/aws-cli:2.37.0"
          command = ["/bin/sh", "-c"]
          args    = [local.litellm_key_registration_script]

          env {
            name = "LITELLM_MASTER_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.litellm.metadata[0].name
                key  = "LITELLM_MASTER_KEY"
              }
            }
          }

          dynamic "env" {
            for_each = local.litellm_virtual_key_consumers
            content {
              name = "KEY_${upper(env.key)}"
              value_from {
                secret_key_ref {
                  name = kubernetes_secret_v1.litellm_virtual_key[env.key].metadata[0].name
                  key  = "LITELLM_API_KEY"
                }
              }
            }
          }

          resources {
            requests = { cpu = "10m", memory = "32Mi" }
            limits   = { cpu = "100m", memory = "128Mi" }
          }
        }
      }
    }
  }

  wait_for_completion = true

  timeouts {
    create = "15m"
  }
}
