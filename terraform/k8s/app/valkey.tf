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
