resource "kubernetes_deployment_v1" "rankings" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-rankings"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 2

    selector {
      match_labels = { app = "pl-rankings" }
    }

    template {
      metadata {
        labels = { app = "pl-rankings", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-rankings"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "rankings"
          image             = local.images.rankings
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
            name  = "POWERLIFTING_S3_BUCKET"
            value = var.dataset_bucket
          }

          env {
            name  = "DATA_DIR"
            value = "/data"
          }

          dynamic "env" {
            for_each = module.workload_aws["pl-rankings"].env
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

          resources {
            limits   = { cpu = "1", memory = "512Mi" }
            requests = { cpu = "50m", memory = "256Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 15
            period_seconds        = 10
            failure_threshold     = 30
          }

          volume_mount {
            name       = "aws"
            mount_path = module.workload_aws["pl-rankings"].mount_path
            read_only  = true
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }
        }

        volume {
          name = "aws"

          dynamic "secret" {
            for_each = module.workload_aws["pl-rankings"].secret_names
            content {
              secret_name = secret.value
            }
          }

          dynamic "projected" {
            for_each = module.workload_aws["pl-rankings"].token_paths
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

        volume {
          name = "data"

          empty_dir {
            size_limit = "1Gi"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "rankings" {
  metadata {
    name      = "pl-rankings"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-rankings" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
