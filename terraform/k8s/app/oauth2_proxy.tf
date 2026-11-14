resource "random_password" "oauth2_proxy_cookie" {
  length  = 32
  special = false
}

data "kubernetes_secret_v1" "authentik_oidc" {
  metadata {
    name      = "authentik-powerlifting-oidc"
    namespace = var.namespace
  }
}

resource "kubernetes_secret_v1" "oauth2_proxy" {
  metadata {
    name      = "oauth2-proxy-secrets"
    namespace = var.namespace
  }

  data = { OAUTH2_PROXY_CLIENT_SECRET = data.kubernetes_secret_v1.authentik_oidc.data["AUTHENTIK_CLIENT_SECRET"] }
}

resource "kubernetes_deployment_v1" "oauth2_proxy" {
  depends_on       = [kubectl_manifest.edge_only, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "oauth2-proxy"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "oauth2-proxy" }
    }

    template {
      metadata {
        labels = { app = "oauth2-proxy", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "oauth2-proxy"
        automount_service_account_token = false

        container {
          name              = "oauth2-proxy"
          image             = "quay.io/oauth2-proxy/oauth2-proxy:v7.15.6"
          image_pull_policy = "IfNotPresent"
          args = [
            "--http-address=0.0.0.0:4180",
            "--reverse-proxy=true",
            "--provider=oidc",
            "--email-domain=*",
            "--redirect-url=https://${var.app_domain}/oauth2/callback",
            "--upstream=http://powerlifting-app-backend.${var.namespace}.svc.cluster.local:3005/",
            "--scope=openid profile email groups roles powerlifting_identity offline_access",
            "--code-challenge-method=S256",
            "--insecure-oidc-skip-nonce=false",
            "--cookie-refresh=1m",
            "--cookie-name=__Host-pl_oauth2_proxy",
            "--cookie-secure=true",
            "--cookie-httponly=true",
            "--cookie-samesite=lax",
            "--session-store-type=redis",
            "--redis-connection-url=redis://pl-valkey.${var.namespace}.svc.cluster.local:6379",
            "--pass-authorization-header=true",
            "--api-route=^/api/.*$",
            "--skip-auth-route=POST=^/api/auth/logout$",
            "--skip-auth-route=GET=^/api/",
            "--upstream-timeout=300s",
            "--skip-provider-button=true",
            "--insecure-oidc-allow-unverified-email=true",
            "--silence-ping-logging=true",
          ]

          env {
            name = "OAUTH2_PROXY_OIDC_ISSUER_URL"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_ISSUER_URL"
              }
            }
          }

          env {
            name = "OAUTH2_PROXY_CLIENT_ID"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_CLIENT_ID"
              }
            }
          }

          env {
            name = "OAUTH2_PROXY_CLIENT_SECRET"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.oauth2_proxy.metadata[0].name
                key  = "OAUTH2_PROXY_CLIENT_SECRET"
              }
            }
          }

          env {
            name  = "OAUTH2_PROXY_COOKIE_SECRET"
            value = random_password.oauth2_proxy_cookie.result
          }

          port {
            name           = "http"
            container_port = 4180
            protocol       = "TCP"
          }

          readiness_probe {
            http_get {
              path = "/ping"
              port = 4180
            }
          }

          resources {
            limits   = { cpu = "250m", memory = "256Mi" }
            requests = { cpu = "25m", memory = "64Mi" }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "oauth2_proxy" {
  metadata {
    name      = "oauth2-proxy"
    namespace = var.namespace
  }

  spec {
    selector = { app = "oauth2-proxy" }

    port {
      name        = "http"
      port        = 4180
      target_port = 4180
      protocol    = "TCP"
    }
  }
}
