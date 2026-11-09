resource "kubernetes_persistent_volume_claim_v1" "prompt_cache" {
  metadata {
    name      = "pl-prompt-cache-data"
    namespace = var.namespace
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = { storage = "2Gi" }
    }
  }

  wait_until_bound = false
}

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
          name              = "qdrant"
          image             = "qdrant/qdrant:v1.15.5"
          image_pull_policy = "IfNotPresent"

          port {
            container_port = 6333
          }

          resources {
            limits   = { cpu = "500m", memory = "512Mi" }
            requests = { cpu = "25m", memory = "96Mi" }
          }

          readiness_probe {
            http_get {
              path = "/readyz"
              port = 6333
            }
            initial_delay_seconds = 3
            period_seconds        = 10
          }

          volume_mount {
            name       = "storage"
            mount_path = "/qdrant/storage"
          }
        }

        volume {
          name = "storage"

          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.prompt_cache.metadata[0].name
          }
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
      port        = 6333
      target_port = 6333
    }
  }
}

resource "kubernetes_deployment_v1" "prompt_cache_mcp" {
  wait_for_rollout = false

  metadata {
    name      = "pl-prompt-cache-mcp"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-prompt-cache-mcp" }
    }

    template {
      metadata {
        labels = { app = "pl-prompt-cache-mcp" }
      }

      spec {
        automount_service_account_token = false
        enable_service_links            = false

        container {
          name              = "mcp"
          image             = "ghcr.io/astral-sh/uv:python3.12-bookworm-slim"
          image_pull_policy = "IfNotPresent"
          command           = ["uvx", "mcp-server-qdrant==0.8.1", "--transport", "streamable-http"]

          env {
            name  = "QDRANT_URL"
            value = "http://pl-prompt-cache.${var.namespace}.svc.cluster.local:6333"
          }

          env {
            name  = "QDRANT_SEARCH_LIMIT"
            value = "5"
          }

          env {
            name  = "FASTMCP_SERVER_HOST"
            value = "0.0.0.0"
          }

          env {
            name  = "FASTMCP_SERVER_PORT"
            value = "8000"
          }

          env {
            name  = "FASTMCP_LOG_LEVEL"
            value = "WARNING"
          }

          env {
            name  = "UV_CACHE_DIR"
            value = "/cache/uv"
          }

          env {
            name  = "FASTEMBED_CACHE_PATH"
            value = "/cache/fastembed"
          }

          port {
            container_port = 8000
          }

          resources {
            limits   = { cpu = "1", memory = "768Mi" }
            requests = { cpu = "25m", memory = "384Mi" }
          }

          readiness_probe {
            tcp_socket {
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          volume_mount {
            name       = "cache"
            mount_path = "/cache"
          }
        }

        volume {
          name = "cache"
          empty_dir {}
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "prompt_cache_mcp" {
  metadata {
    name      = "pl-prompt-cache-mcp"
    namespace = var.namespace
  }

  spec {
    selector = { app = "pl-prompt-cache-mcp" }

    port {
      port        = 8000
      target_port = 8000
    }
  }
}
