moved {
  from = kubernetes_deployment_v1.service["pl-sessions"]
  to   = kubernetes_deployment_v1.sessions
}

moved {
  from = kubernetes_service_v1.service["pl-sessions"]
  to   = kubernetes_service_v1.sessions
}

resource "kubernetes_deployment_v1" "sessions" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-sessions"
    namespace = var.namespace
  }

  spec {
    replicas = 2

    selector {
      match_labels = { app = "pl-sessions" }
    }

    template {
      metadata {
        labels = { app = "pl-sessions", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-sessions"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "sessions"
          image             = local.images.sessions
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "HTTP_ADDR"
            value = ":8000"
          }

          env {
            name  = "GOMEMLIMIT"
            value = "100MiB"
          }

          env {
            name  = "PL_PROFILE_URL"
            value = "http://pl-profile.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "VALKEY_URL"
            value = local.service_env.VALKEY_URL
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

resource "kubernetes_service_v1" "sessions" {
  metadata {
    name      = "pl-sessions"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-sessions" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
