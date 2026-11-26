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

  data = {
    OAUTH2_PROXY_CLIENT_SECRET = data.kubernetes_secret_v1.authentik_oidc.data["AUTHENTIK_CLIENT_SECRET"]
    OAUTH2_PROXY_COOKIE_SECRET = random_password.oauth2_proxy_cookie.result
  }
}
