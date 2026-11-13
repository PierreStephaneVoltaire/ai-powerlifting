resource "kubernetes_deployment_v1" "analytics_ai" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-analytics-ai"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-analytics-ai" }
    }

    template {
      metadata {
        labels = { app = "pl-analytics-ai", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-analytics-ai"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "analytics-ai"
          image             = local.images.analytics_ai
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
            name  = "IF_API_URL"
            value = local.service_env.IF_API_URL
          }

          env {
            name  = "ANALYTICS_GRPC_URL"
            value = "pl-analytics.${var.namespace}.svc.cluster.local:50051"
          }

          env {
            name  = "EXPORT_GRPC_URL"
            value = "pl-analytics-export.${var.namespace}.svc.cluster.local:50051"
          }

          env {
            name  = "AI_GRPC_ALLOWED_CALLERS"
            value = "pl-analytics"
          }

          env {
            name  = "AWS_SHARED_CREDENTIALS_FILE"
            value = "/secrets/aws/credentials"
          }

          env {
            name  = "AWS_CONFIG_FILE"
            value = "/secrets/aws/config"
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }

          port {
            container_port = 8000
            name           = "http"
            protocol       = "TCP"
          }

          port {
            container_port = 50051
            name           = "grpc"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "500m", memory = "128Mi" }
            requests = { cpu = "25m", memory = "32Mi" }
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

resource "kubernetes_service_v1" "analytics_ai" {
  metadata {
    name      = "pl-analytics-ai"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-analytics-ai" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }

    port {
      port         = 50051
      target_port  = 50051
      name         = "grpc"
      protocol     = "TCP"
      app_protocol = "grpc"
    }
  }
}
