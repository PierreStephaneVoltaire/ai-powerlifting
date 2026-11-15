resource "kubectl_manifest" "assistant_workflow_state" {
  yaml_body = yamlencode({
    apiVersion = "dapr.io/v1alpha1"
    kind       = "Component"
    metadata   = { name = "assistant-workflow-state", namespace = var.namespace }
    spec = {
      type    = "state.postgresql"
      version = "v2"
      metadata = [
        { name = "actorStateStore", value = "true" },
        { name = "host", secretKeyRef = { name = "assistant-postgres-connection", key = "host" } },
        { name = "port", secretKeyRef = { name = "assistant-postgres-connection", key = "port" } },
        { name = "database", secretKeyRef = { name = "assistant-postgres-connection", key = "dbname" } },
        { name = "user", secretKeyRef = { name = "assistant-postgres-connection", key = "user" } },
        { name = "password", secretKeyRef = { name = "assistant-postgres-connection", key = "password" } },
      ]
      scopes = ["pl-assistant"]
    }
    auth = { secretStore = "kubernetes" }
  })
}

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
    name      = kubernetes_service_account_v1.assistant.metadata[0].name
    namespace = var.namespace
  }
}
