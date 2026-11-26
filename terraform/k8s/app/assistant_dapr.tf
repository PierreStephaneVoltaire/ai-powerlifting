resource "kubernetes_role_v1" "assistant_secret_reader" {
  metadata {
    name      = "pl-assistant-secret-reader"
    namespace = var.namespace
  }
  rule {
    api_groups     = [""]
    resources      = ["secrets"]
    resource_names = ["assistant-postgres-connection"]
    verbs          = ["get"]
  }
}

resource "kubernetes_role_binding_v1" "assistant_secret_reader" {
  metadata {
    name      = "pl-assistant-secret-reader"
    namespace = var.namespace
  }
  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "Role"
    name      = kubernetes_role_v1.assistant_secret_reader.metadata[0].name
  }
  subject {
    kind      = "ServiceAccount"
    name      = "pl-assistant"
    namespace = var.namespace
  }
}
