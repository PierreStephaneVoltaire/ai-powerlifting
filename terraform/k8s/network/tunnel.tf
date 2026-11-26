data "kubernetes_secret_v1" "tunnel" {
  metadata {
    name      = "cloudflared-token"
    namespace = var.namespace
  }
}
