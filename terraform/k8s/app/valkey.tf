resource "kubernetes_persistent_volume_claim_v1" "valkey" {
  metadata {
    name      = "pl-valkey-data"
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

resource "kubernetes_deployment_v1" "valkey" {
  wait_for_rollout = false

  metadata {
    name      = "pl-valkey"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = { app = "pl-valkey" }
    }

    template {
      metadata {
        labels = { app = "pl-valkey" }
      }

      spec {
        automount_service_account_token = false

        container {
          name              = "valkey"
          image             = "valkey/valkey:7.2.5"
          image_pull_policy = "IfNotPresent"
          args              = ["--save", "3600", "1", "--appendonly", "no", "--maxmemory", "1gb", "--maxmemory-policy", "allkeys-lru"]

          port {
            container_port = 6379
          }

          resources {
            limits   = { cpu = "500m", memory = "1280Mi" }
            requests = { cpu = "100m", memory = "128Mi" }
          }

          volume_mount {
            name       = "data"
            mount_path = "/data"
          }

          liveness_probe {
            exec {
              command = ["valkey-cli", "ping"]
            }
            initial_delay_seconds = 10
            period_seconds        = 15
            timeout_seconds       = 3
          }

          readiness_probe {
            exec {
              command = ["valkey-cli", "ping"]
            }
            initial_delay_seconds = 3
            period_seconds        = 5
            timeout_seconds       = 2
          }
        }

        volume {
          name = "data"

          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.valkey.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "valkey" {
  metadata {
    name      = "pl-valkey"
    namespace = var.namespace
  }

  spec {
    selector = { app = "pl-valkey" }

    port {
      port        = 6379
      target_port = 6379
    }
  }
}
