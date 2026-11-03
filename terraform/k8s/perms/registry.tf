resource "kubernetes_service_account_v1" "registry_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = var.namespace
  }
}

resource "kubernetes_role_v1" "registry_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = var.namespace
  }

  rule {
    api_groups     = [""]
    resources      = ["secrets"]
    resource_names = ["ecr-registry"]
    verbs          = ["get", "patch"]
  }
}

resource "kubernetes_role_binding_v1" "registry_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = var.namespace
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.registry_refresher.metadata[0].name
    namespace = var.namespace
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.registry_refresher.metadata[0].name
  }
}
