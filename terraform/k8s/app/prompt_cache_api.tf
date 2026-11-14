resource "kubernetes_secret_v1" "prompt_cache_api" {
  metadata {
    name      = "pl-prompt-cache-api"
    namespace = var.namespace
  }

  data = {
    OPENAI_API_KEY = lookup(local.litellm_provider_keys, "openai", "")
  }
}

resource "kubernetes_deployment_v1" "prompt_cache_api" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-prompt-cache-api"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-prompt-cache-api" }
    }

    template {
      metadata {
        labels = { app = "pl-prompt-cache-api", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-prompt-cache-api"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "prompt-cache-api"
          image             = local.images.prompt_cache_api
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "VALKEY_URL"
            value = local.service_env.VALKEY_URL
          }

          env {
            name  = "PROMPT_CACHE_MCP_URL"
            value = local.service_env.PROMPT_CACHE_MCP_URL
          }

          env {
            name = "OPENAI_API_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.prompt_cache_api.metadata[0].name
                key  = "OPENAI_API_KEY"
              }
            }
          }

          port {
            container_port = 8000
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "500m", memory = "256Mi" }
            requests = { cpu = "25m", memory = "32Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 2
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "prompt_cache_api" {
  metadata {
    name      = "pl-prompt-cache-api"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-prompt-cache-api" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
