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
