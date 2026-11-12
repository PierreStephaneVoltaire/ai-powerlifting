data "kubernetes_secret_v1" "tunnel" {
  metadata {
    name      = "cloudflared-token"
    namespace = var.namespace
  }
}

resource "kubernetes_deployment_v1" "tunnel" {
  wait_for_rollout = false

  metadata {
    name      = "cloudflared"
    namespace = var.namespace
  }

  spec {
    replicas = 2

    selector {
      match_labels = { app = "cloudflared" }
    }

    template {
      metadata {
        labels      = { app = "cloudflared", "istio.io/dataplane-mode" = "ambient" }
        annotations = { "checksum/token" = sha256(data.kubernetes_secret_v1.tunnel.data["token"]) }
      }

      spec {
        service_account_name            = "cloudflared"
        automount_service_account_token = false

        container {
          name  = "cloudflared"
          image = "cloudflare/cloudflared:2024.10.1"
          args  = ["tunnel", "--no-autoupdate", "--metrics", "0.0.0.0:2000", "run"]

          env {
            name = "TUNNEL_TOKEN"
            value_from {
              secret_key_ref {
                name = "cloudflared-token"
                key  = "token"
              }
            }
          }

          liveness_probe {
            http_get {
              path = "/ready"
              port = 2000
            }
            initial_delay_seconds = 10
            period_seconds        = 10
            failure_threshold     = 3
          }

          resources {
            requests = { cpu = "50m", memory = "64Mi" }
            limits   = { cpu = "200m", memory = "128Mi" }
          }
        }
      }
    }
  }
}
