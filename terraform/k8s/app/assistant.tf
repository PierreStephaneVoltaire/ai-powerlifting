locals {
  assistant_mcp_aliases = join(",", sort(keys(local.litellm_mcp_registry)))
  assistant_models = {
    PL_MODEL_COORDINATOR    = "pl-coordinator"
    PL_MODEL_RESPONDER_FAST = "pl-responder-fast"
    PL_MODEL_SECURITY       = "pl-light"
    PL_MODEL_EMBED          = "pl-embed"
    PL_MODEL_STRONG         = "pl-strong"
  }
  assistant_postgres_keys = {
    PGHOST     = "host"
    PGPORT     = "port"
    PGDATABASE = "dbname"
    PGUSER     = "user"
    PGPASSWORD = "password"
  }
}

resource "kubernetes_service_account_v1" "assistant" {
  metadata {
    name      = "pl-assistant"
    namespace = var.namespace
  }
  automount_service_account_token = false
}

resource "kubernetes_deployment_v1" "assistant" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls, kubectl_manifest.assistant_workflow_state, kubectl_manifest.assistant_dapr_peers]
  wait_for_rollout = false

  metadata {
    name      = "pl-assistant"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 3

    strategy {
      type = "RollingUpdate"
    }

    selector {
      match_labels = { app = "pl-assistant" }
    }

    template {
      metadata {
        labels = { app = "pl-assistant", "istio.io/dataplane-mode" = "ambient" }
        annotations = {
          "dapr.io/enabled"                = "true"
          "dapr.io/app-id"                 = "pl-assistant"
          "dapr.io/app-port"               = "8000"
          "dapr.io/app-protocol"           = "http"
          "dapr.io/sidecar-cpu-request"    = "50m"
          "dapr.io/sidecar-cpu-limit"      = "500m"
          "dapr.io/sidecar-memory-request" = "128Mi"
          "dapr.io/sidecar-memory-limit"   = "256Mi"
        }
      }

      spec {
        service_account_name             = kubernetes_service_account_v1.assistant.metadata[0].name
        automount_service_account_token  = true
        enable_service_links             = false
        termination_grace_period_seconds = 60

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "assistant"
          image             = local.images.assistant
          image_pull_policy = "IfNotPresent"

          env {
            name  = "HTTP_ADDR"
            value = ":8000"
          }

          env {
            name  = "GOMEMLIMIT"
            value = "1792MiB"
          }

          dynamic "env" {
            for_each = local.assistant_postgres_keys
            content {
              name = env.key
              value_from {
                secret_key_ref {
                  name = "assistant-postgres-connection"
                  key  = env.value
                }
              }
            }
          }

          env {
            name  = "PGSSLMODE"
            value = "prefer"
          }

          env {
            name  = "LITELLM_BASE_URL"
            value = "http://litellm.${var.namespace}.svc.cluster.local:4000"
          }

          env {
            name = "LITELLM_API_KEY"
            value_from {
              secret_key_ref {
                name = "litellm-virtual-key-assistant"
                key  = "LITELLM_API_KEY"
              }
            }
          }

          dynamic "env" {
            for_each = local.assistant_mcp_aliases == "" ? {} : { LITELLM_MCP_ALIASES = local.assistant_mcp_aliases }
            content {
              name  = env.key
              value = env.value
            }
          }

          env {
            name  = "PL_PROFILE_URL"
            value = "http://pl-profile.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name = "PL_JOB_TOKEN_PRIVATE_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.assistant_job_token.metadata[0].name
                key  = "PL_JOB_TOKEN_PRIVATE_KEY"
              }
            }
          }

          dynamic "env" {
            for_each = local.assistant_models
            content {
              name  = env.key
              value = env.value
            }
          }

          port {
            container_port = 8000
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "1", memory = "2Gi" }
            requests = { cpu = "250m", memory = "512Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "assistant" {
  metadata {
    name      = "pl-assistant"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-assistant" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
