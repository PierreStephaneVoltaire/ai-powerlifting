moved {
  from = kubernetes_deployment_v1.service["pl-profile"]
  to   = kubernetes_deployment_v1.profile
}

moved {
  from = kubernetes_service_v1.service["pl-profile"]
  to   = kubernetes_service_v1.profile
}

resource "kubernetes_deployment_v1" "profile" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-profile"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-profile" }
    }

    template {
      metadata {
        labels = { app = "pl-profile", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-profile"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "profile"
          image             = local.images.profile
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
            value = "200MiB"
          }

          env {
            name  = "PL_SERVICE_URL_TEMPLATE"
            value = local.service_env.PL_SERVICE_URL_TEMPLATE
          }

          env {
            name  = "VALKEY_URL"
            value = local.service_env.VALKEY_URL
          }

          env {
            name = "DISCORD_BOT_TOKEN"
            value_from {
              secret_key_ref {
                name = "powerlifting-profile-secrets"
                key  = "DISCORD_BOT_TOKEN"
              }
            }
          }

          env {
            name  = "AWS_SHARED_CREDENTIALS_FILE"
            value = "/secrets/aws/credentials"
          }

          env {
            name  = "AWS_CONFIG_FILE"
            value = "/secrets/aws/config"
          }

          env {
            name  = "PL_JOB_TOKEN_PUBLIC_KEY"
            value = local.job_token_public_key
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
            limits   = { cpu = "500m", memory = "256Mi" }
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

resource "kubernetes_service_v1" "profile" {
  metadata {
    name      = "pl-profile"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-profile" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
