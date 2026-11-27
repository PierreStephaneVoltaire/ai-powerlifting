resource "kubernetes_secret_v1" "server_join" {
  metadata {
    name      = "nolift-tailnet-server"
    namespace = "cattle-system"
  }
  data = { key = "${tailscale_oauth_client.server_join.key}?ephemeral=false&preauthorized=true" }
}
