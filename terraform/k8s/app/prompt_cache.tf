resource "kubernetes_deployment_v1" "prompt_cache" {
  wait_for_rollout = false

  metadata {
    name      = "pl-prompt-cache"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = { app = "pl-prompt-cache" }
    }

    template {
      metadata {
        labels = { app = "pl-prompt-cache" }
      }

      spec {
        automount_service_account_token = false
        enable_service_links            = false

        container {
          name              = "postgres"
          image             = "pgvector/pgvector:pg17"
          image_pull_policy = "IfNotPresent"

          env {
            name  = "POSTGRES_USER"
            value = "prompt_cache"
          }

          env {
            name  = "POSTGRES_DB"
            value = "prompt_cache"
          }

          env {
            name = "POSTGRES_PASSWORD"
            value_from {
              secret_key_ref {
                name = "powerlifting-app-secrets"
                key  = "PROMPT_CACHE_PASSWORD"
              }
            }
          }

          env {
            name  = "PGDATA"
            value = "/var/lib/postgresql/data/pgdata"
          }

          port {
            container_port = 5432
          }

          resources {
            limits   = { cpu = "500m", memory = "512Mi" }
            requests = { cpu = "25m", memory = "96Mi" }
          }

          readiness_probe {
            exec {
              command = ["pg_isready", "-U", "prompt_cache", "-d", "prompt_cache"]
            }
            initial_delay_seconds = 5
            period_seconds        = 10
          }

          volume_mount {
            name       = "postgres"
            mount_path = "/var/lib/postgresql/data"
          }
        }

        container {
          name              = "embeddings"
          image             = "ghcr.io/huggingface/text-embeddings-inference:cpu-1.8"
          image_pull_policy = "IfNotPresent"
          args              = ["--model-id", "jinaai/jina-embeddings-v2-small-en", "--port", "8080", "--auto-truncate"]

          env {
            name  = "HUGGINGFACE_HUB_CACHE"
            value = "/data"
          }

          port {
            container_port = 8080
          }

          resources {
            limits   = { cpu = "1", memory = "1Gi" }
            requests = { cpu = "50m", memory = "256Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8080
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          volume_mount {
            name       = "models"
            mount_path = "/data"
          }
        }

        volume {
          name = "postgres"
          empty_dir {}
        }

        volume {
          name = "models"
          empty_dir {}
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "prompt_cache" {
  metadata {
    name      = "pl-prompt-cache"
    namespace = var.namespace
  }

  spec {
    selector = { app = "pl-prompt-cache" }

    port {
      name        = "postgres"
      port        = 5432
      target_port = 5432
    }

    port {
      name        = "embeddings"
      port        = 8080
      target_port = 8080
    }
  }
}
