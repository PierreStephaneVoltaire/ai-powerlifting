resource "kubernetes_namespace_v1" "powerlifting" {
  metadata {
    name = var.namespace
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}
resource "kubernetes_namespace_v1" "monitoring" {
  metadata {
    name = "monitoring"
    labels = {
      app        = "observability"
      managed-by = "terraform"
    }
  }

  lifecycle {
    ignore_changes = [
      metadata[0].annotations,
    ]
  }
}
