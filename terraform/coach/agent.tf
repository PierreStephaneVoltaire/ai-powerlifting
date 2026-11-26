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
