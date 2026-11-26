resource "helm_release" "argocd" {
  name             = "argocd"
  namespace        = "argocd"
  create_namespace = true
  repository       = "https://argoproj.github.io/argo-helm"
  chart            = "argo-cd"
  version          = "10.20.0"

  values = [yamlencode({
    global         = { image = { repository = "quay.io/argoproj/argocd" } }
    redis          = { image = { repository = "public.ecr.aws/docker/library/redis" } }
    dex            = { enabled = false }
    applicationSet = { replicas = 0 }
    configs = {
      params = { "server.insecure" = true }
      cm = {
        url                                  = "https://${var.argocd_domain}"
        "timeout.reconciliation"             = "0s"
        "admin.enabled"                      = false
        "application.resourceTrackingMethod" = "annotation"
        "oidc.config"                        = local.oidc_config
      }
      secret = { extra = { "oidc.authentik.clientSecret" = var.argocd_client_secret } }
      rbac = {
        "policy.default" = ""
        "policy.csv"     = "g, argocd-admins, role:admin"
        scopes           = "[groups]"
      }
    }
  })]
}

resource "helm_release" "argocd_image_updater" {
  name       = "argocd-image-updater"
  namespace  = helm_release.argocd.namespace
  repository = helm_release.argocd.repository
  chart      = "argocd-image-updater"
  version    = "1.5.0"

  values = [yamlencode({
    image              = { repository = "quay.io/argoprojlabs/argocd-image-updater", tag = "v1.5.1" }
    replicaCount       = var.argocd_auto_sync ? 1 : 0
    createClusterRoles = false
    config = {
      interval = "2m"
      registries = [{
        name        = "ecr"
        prefix      = local.ecr
        api_url     = "https://${local.ecr}"
        credentials = "pullsecret:${var.namespace}/ecr-registry"
        credsexpire = "5h"
      }]
    }
  })]
  depends_on = [kubectl_manifest.application]
}

resource "kubernetes_role_v1" "ecr_reader" {
  metadata {
    name      = "argocd-image-updater"
    namespace = var.namespace
  }
  rule {
    api_groups     = [""]
    resources      = ["secrets"]
    resource_names = ["ecr-registry"]
    verbs          = ["get"]
  }
}

resource "kubernetes_role_binding_v1" "ecr_reader" {
  metadata {
    name      = "argocd-image-updater"
    namespace = var.namespace
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.ecr_reader.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = helm_release.argocd_image_updater.name
    namespace = helm_release.argocd_image_updater.namespace
  }
}
