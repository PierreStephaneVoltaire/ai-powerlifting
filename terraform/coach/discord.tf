resource "kubernetes_deployment_v1" "coach_discord" {
  wait_for_rollout = false

  metadata {
    name      = "pl-coach-discord"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-coach-discord" }
    }

    template {
      metadata {
        labels = { app = "pl-coach-discord" }
      }

      spec {
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = var.image_pull_secret
        }

        container {
          name              = "relay"
          image             = "${data.aws_ecr_repository.coach["if-powerlifting-coach-discord"].repository_url}@${data.aws_ecr_image.coach["if-powerlifting-coach-discord"].image_digest}"
          image_pull_policy = "IfNotPresent"

          env {
            name  = "COACH_URL"
            value = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "DISCORD_OPERATOR_ID"
            value = var.discord_operator_id
          }

          env {
            name  = "OPERATOR_PERSON"
            value = var.operator_person
          }

          env {
            name  = "DISCORD_PERSONS"
            value = jsonencode(var.discord_persons)
          }

          env {
            name = "INTERNAL_API_TOKEN"
            value_from {
              secret_key_ref {
                name = var.shared_secret_name
                key  = "INTERNAL_API_TOKEN"
              }
            }
          }

          env {
            name = "DISCORD_TOKEN"
            value_from {
              secret_key_ref {
                name = var.discord_secret_name
                key  = "DISCORD_TOKEN"
              }
            }
          }

          port {
            container_port = 8000
          }

          resources {
            limits   = { cpu = "250m", memory = "192Mi" }
            requests = { cpu = "10m", memory = "48Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 3
            period_seconds        = 10
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "coach_discord" {
  wait_for_load_balancer = false

  metadata {
    name      = "pl-coach-discord"
    namespace = var.namespace
  }

  spec {
    selector = { app = "pl-coach-discord" }

    port {
      port        = 8000
      target_port = 8000
    }

    type = "ClusterIP"
  }
}
