resource "kubernetes_deployment_v1" "analytics" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-analytics"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-analytics" }
    }

    template {
      metadata {
        labels = { app = "pl-analytics", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-analytics"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "analytics"
          image             = local.images.analytics
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "BUILD_ID"
            value = local.images.analytics
          }

          env {
            name  = "VALKEY_URL"
            value = local.service_env.VALKEY_URL
          }

          env {
            name  = "ANALYTICS_AI_GRPC_URL"
            value = "http://pl-analytics-ai.${var.namespace}.svc.cluster.local:50051"
          }

          env {
            name  = "GRPC_ALLOWED_CALLERS"
            value = "pl-analytics-ai,pl-analytics-export"
          }

          env {
            name  = "POWERLIFTING_S3_BUCKET"
            value = var.dataset_bucket
          }

          dynamic "env" {
            for_each = module.workload_aws["pl-analytics"].env
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
            limits   = { cpu = "1", memory = "256Mi" }
            requests = { cpu = "50m", memory = "64Mi" }
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
            mount_path = module.workload_aws["pl-analytics"].mount_path
            read_only  = true
          }
        }

        volume {
          name = "aws"

          dynamic "secret" {
            for_each = module.workload_aws["pl-analytics"].secret_names
            content {
              secret_name = secret.value
            }
          }

          dynamic "projected" {
            for_each = module.workload_aws["pl-analytics"].token_paths
            content {
              sources {
                service_account_token {
                  audience           = "sts.amazonaws.com"
                  expiration_seconds = 3600
                  path               = projected.value
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "analytics" {
  metadata {
    name      = "pl-analytics"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-analytics" }

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
