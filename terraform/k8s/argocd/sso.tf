locals {
  oidc_config = yamlencode({
    name            = "Authentik"
    issuer          = "https://${var.auth_domain}/application/o/argocd/"
    clientID        = "nolift-argocd"
    clientSecret    = "$oidc.authentik.clientSecret"
    requestedScopes = ["openid", "profile", "email", "groups"]
  })
}

resource "kubectl_manifest" "argocd_backend" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1beta1"
    kind       = "ReferenceGrant"
    metadata   = { name = "nolift-argocd-server", namespace = "argocd" }
    spec = {
      from = [{ group = "gateway.networking.k8s.io", kind = "HTTPRoute", namespace = var.namespace }]
      to   = [{ group = "", kind = "Service", name = "argocd-server" }]
    }
  })
  depends_on = [helm_release.argocd]
}
