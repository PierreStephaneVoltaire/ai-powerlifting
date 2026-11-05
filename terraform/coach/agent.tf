resource "kubernetes_persistent_volume_claim_v1" "coach_state" {
  metadata {
    name      = "pl-coach-state"
    namespace = var.namespace
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = "local-path-wait"
    volume_mode        = "Filesystem"

    resources {
      requests = {
        storage = "2Gi"
      }
    }
  }

  wait_until_bound = false

  lifecycle {
    ignore_changes = [metadata[0].annotations, spec[0].volume_name]
  }
}

resource "kubernetes_deployment_v1" "coach" {
  wait_for_rollout = false

  lifecycle {
    precondition {
      condition     = var.coach_replicas == 1 || alltrue([for provider in values(var.coach_providers) : provider.auth != "chatgpt"])
      error_message = "The ChatGPT subscription login can only run in one Coach pod; set coach_replicas = 1 or move every operation to an api_key provider."
    }
  }

  metadata {
    name      = "pl-coach"
    namespace = var.namespace
  }

  spec {
    replicas = var.coach_replicas

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = { app = "pl-coach" }
    }

    template {
      metadata {
        labels = { app = "pl-coach" }
      }

      spec {
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 60
        node_selector                    = { "kubernetes.io/hostname" = var.node_name }

        image_pull_secrets {
          name = var.image_pull_secret
        }

        security_context {
          fs_group = 10001
        }

        container {
          name              = "coach"
          image             = "${data.aws_ecr_repository.coach["if-powerlifting-coach-agent"].repository_url}@${data.aws_ecr_image.coach["if-powerlifting-coach-agent"].image_digest}"
          image_pull_policy = "IfNotPresent"

          env {
            name  = "COACH_URL"
            value = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "PL_SERVICE_URL_TEMPLATE"
            value = "http://pl-{domain}.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "PL_PROFILE_URL"
            value = "http://pl-profile.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "COACH_PROVIDERS"
            value = jsonencode(var.coach_providers)
          }

          env {
            name  = "COACH_CONVERSATION_AI"
            value = jsonencode(var.conversation_ai)
          }

          env {
            name  = "COACH_OPERATION_AI"
            value = jsonencode(var.operation_ai)
          }

          env {
            name = "COACH_PROVIDER_KEYS"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.provider_keys.metadata[0].name
                key  = "COACH_PROVIDER_KEYS"
              }
            }
          }

          dynamic "env" {
            for_each = toset(["INTERNAL_API_TOKEN", "PL_PRINCIPAL_SECRET"])
            content {
              name = env.value
              value_from {
                secret_key_ref {
                  name = var.shared_secret_name
                  key  = env.value
                }
              }
            }
          }

          port {
            container_port = 8000
          }

          resources {
            limits   = { cpu = "1", memory = "1536Mi" }
            requests = { cpu = "50m", memory = "192Mi" }
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
            name       = "state"
            mount_path = "/var/lib/coach"
          }
        }

        volume {
          name = "state"

          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.coach_state.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "coach" {
  wait_for_load_balancer = false

  metadata {
    name      = "pl-coach"
    namespace = var.namespace
  }

  spec {
    selector = { app = "pl-coach" }

    port {
      port        = 8000
      target_port = 8000
    }

    type = "ClusterIP"
  }
}
