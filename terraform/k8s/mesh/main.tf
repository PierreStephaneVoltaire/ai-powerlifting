resource "kubernetes_namespace_v1" "istio_system" {
  metadata {
    name = "istio-system"
  }
}

resource "helm_release" "base" {
  name             = "istio-base"
  repository       = "https://blob.istio.io/istio-release/charts"
  chart            = "base"
  version          = "1.32.0"
  namespace        = kubernetes_namespace_v1.istio_system.metadata[0].name
  create_namespace = false
  wait             = true
}

resource "helm_release" "istiod" {
  name       = "istiod"
  repository = "https://blob.istio.io/istio-release/charts"
  chart      = "istiod"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values     = [yamlencode({ profile = "ambient" })]
  depends_on = [helm_release.base]
}

resource "helm_release" "cni" {
  name       = "istio-cni"
  repository = "https://blob.istio.io/istio-release/charts"
  chart      = "cni"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values     = [yamlencode({ profile = "ambient", global = { platform = "k3s" } })]
  depends_on = [helm_release.istiod]
}

resource "helm_release" "ztunnel" {
  name       = "ztunnel"
  repository = "https://blob.istio.io/istio-release/charts"
  chart      = "ztunnel"
  version    = "1.32.0"
  namespace  = kubernetes_namespace_v1.istio_system.metadata[0].name
  wait       = true

  values     = [yamlencode({ profile = "ambient" })]
  depends_on = [helm_release.cni]
}
