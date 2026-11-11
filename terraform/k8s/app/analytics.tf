resource "kubernetes_deployment_v1" "analytics" {
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
          image             = local.images.services
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PL_DOMAIN"
            value = "analytics"
          }

          env {
            name  = "ANALYTICS_NODE_URL"
            value = "http://127.0.0.1:8091"
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

          env {
            name  = "PL_SECURITY_URL"
            value = "http://pl-security.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name = "PL_PRINCIPAL_PUBLIC_KEY"
            value_from {
              secret_key_ref {
                name = "pl-security-signing-key"
                key  = "public_key"
              }
            }
          }

          env {
            name = "ANALYTICS_NODE_TOKEN"
            value_from {
              secret_key_ref {
                name = "powerlifting-app-secrets"
                key  = "ANALYTICS_NODE_TOKEN"
              }
            }
          }

          port {
            container_port = 8000
          }

          resources {
            limits   = { cpu = "500m", memory = "512Mi" }
            requests = { cpu = "25m", memory = "64Mi" }
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

        container {
          name              = "reports"
          image             = local.images.analytics
          image_pull_policy = "IfNotPresent"

          env {
            name  = "ANALYTICS_NODE_PORT"
            value = "8091"
          }

          dynamic "env" {
            for_each = local.service_env
            content {
              name  = env.key
              value = env.value
            }
          }

          env {
            name = "ANALYTICS_NODE_TOKEN"
            value_from {
              secret_key_ref {
                name = "powerlifting-app-secrets"
                key  = "ANALYTICS_NODE_TOKEN"
              }
            }
          }

          resources {
            limits   = { cpu = "1", memory = "512Mi" }
            requests = { cpu = "50m", memory = "128Mi" }
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
  }
}
