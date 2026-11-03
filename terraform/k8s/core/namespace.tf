resource "kubernetes_namespace_v1" "powerlifting" {
  metadata {
    name = var.namespace
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}
