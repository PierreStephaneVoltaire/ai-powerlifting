locals {
  service_env = {
    IF_API_URL                  = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
    VALKEY_URL                  = "redis://pl-valkey.${var.namespace}.svc.cluster.local:6379"
    PROMPT_CACHE_QDRANT_URL     = "http://pl-prompt-cache.${var.namespace}.svc.cluster.local:6333"
    PROMPT_CACHE_MCP_URL        = "http://pl-prompt-cache-mcp.${var.namespace}.svc.cluster.local:8000/mcp"
    AWS_SHARED_CREDENTIALS_FILE = "/secrets/aws/credentials"
    AWS_CONFIG_FILE             = "/secrets/aws/config"
  }

  small = { limits = { cpu = "500m", memory = "256Mi" }, requests = { cpu = "25m", memory = "64Mi" } }

  services = {
    "pl-budget"        = merge(local.small, { domain = "budget" })
    "pl-calculations"  = merge(local.small, { domain = "calculations" })
    "pl-competition"   = merge(local.small, { domain = "competition" })
    "pl-export"        = { domain = "export", limits = { cpu = "1", memory = "512Mi" }, requests = { cpu = "50m", memory = "128Mi" } }
    "pl-federation"    = merge(local.small, { domain = "federation" })
    "pl-glossary"      = merge(local.small, { domain = "glossary" })
    "pl-goals"         = merge(local.small, { domain = "goals" })
    "pl-imports"       = merge(local.small, { domain = "imports" })
    "pl-lift-profiles" = merge(local.small, { domain = "lift-profiles" })
    "pl-performance"   = merge(local.small, { domain = "performance" })
    "pl-profile"       = merge(local.small, { domain = "profile" })
    "pl-program"       = merge(local.small, { domain = "program" })
    "pl-rankings"      = { domain = "rankings", limits = { cpu = "1", memory = "3Gi" }, requests = { cpu = "25m", memory = "768Mi" } }
    "pl-sessions"      = merge(local.small, { domain = "sessions" })
    "pl-templates"     = merge(local.small, { domain = "templates" })
    "pl-videos"        = merge(local.small, { domain = "videos" })
    "pl-weight-log"    = merge(local.small, { domain = "weight-log" })
  }
}

resource "kubernetes_deployment_v1" "service" {
  depends_on = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  for_each   = local.services

  wait_for_rollout = false

  metadata {
    name      = each.key
    namespace = var.namespace
  }

  spec {
    replicas = each.key == "pl-sessions" ? 2 : 1

    selector {
      match_labels = { app = each.key }
    }

    template {
      metadata {
        labels = { app = each.key, "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = each.key
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = each.value.domain
          image             = local.images.services
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PL_DOMAIN"
            value = each.value.domain
          }

          env {
            name  = "POWERLIFTING_S3_BUCKET"
            value = var.dataset_bucket
          }

          dynamic "env" {
            for_each = local.service_env
            content {
              name  = env.key
              value = env.value
            }
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }


          dynamic "env" {
            for_each = each.key == "pl-profile" ? [1] : []
            content {
              name = "DISCORD_BOT_TOKEN"
              value_from {
                secret_key_ref {
                  name = "powerlifting-profile-secrets"
                  key  = "DISCORD_BOT_TOKEN"
                }
              }
            }
          }

          port {
            container_port = 8000
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = each.value.limits
            requests = each.value.requests
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 3
            period_seconds        = 10
          }

          volume_mount {
            name       = "aws"
            mount_path = "/secrets/aws"
            read_only  = true
          }
        }

        volume {
          name = "aws"

          secret {
            secret_name = "pl-aws-credentials"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "service" {
  for_each = local.services

  metadata {
    name      = each.key
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = each.key }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
