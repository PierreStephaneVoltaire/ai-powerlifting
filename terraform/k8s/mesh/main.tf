resource "kubernetes_namespace_v1" "istio_system" {
  metadata {
    name = "istio-system"
  }
}

locals {
  authz_destinations = merge(
    { "pl-security" = 9000, "pl-coach" = 9001 },
    { for index, name in ["analytics", "budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "pl-${name}" => 9002 + index },
    { "pl-coach-discord" = 9020, "pl-backend" = 9021 },
  )
}

resource "helm_release" "base" {
  name             = "istio-base"
  repository       = "https://istio-release.storage.googleapis.com/charts"
  chart            = "base"
  version          = "1.32.0"
  namespace        = kubernetes_namespace_v1.istio_system.metadata[0].name
  create_namespace = false
  wait             = true
}

resource "helm_release" "istiod" {
  name       = "istiod"
  repository = "https://istio-release.storage.googleapis.com/charts"
  chart      = "istiod"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values = [yamlencode({
    profile = "ambient"
    meshConfig = { extensionProviders = [for destination, port in local.authz_destinations : {
      name = "nolift-${destination}"
      envoyExtAuthzGrpc = {
        service  = "pl-security.${var.namespace}.svc.cluster.local"
        port     = port
        timeout  = "2s"
        failOpen = false
        includeRequestBodyInCheck = {
          maxRequestBytes     = 10485760
          allowPartialMessage = false
          packAsBytes         = true
        }
        includeRequestHeadersInCheck = ["authorization", "content-type", "x-pl-principal"]
        headersToUpstreamOnAllow     = ["x-pl-principal", "x-pl-mesh-caller"]
      }
    }] }
  })]
  depends_on = [helm_release.base]
}

resource "helm_release" "cni" {
  name       = "istio-cni"
  repository = "https://istio-release.storage.googleapis.com/charts"
  chart      = "cni"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values     = [yamlencode({ profile = "ambient", global = { platform = "k3s" } })]
  depends_on = [helm_release.istiod]
}

resource "helm_release" "ztunnel" {
  name       = "ztunnel"
  repository = "https://istio-release.storage.googleapis.com/charts"
  chart      = "ztunnel"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values     = [yamlencode({ profile = "ambient" })]
  depends_on = [helm_release.cni]
}
