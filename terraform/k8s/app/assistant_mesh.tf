resource "kubectl_manifest" "assistant_dapr_peers" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "pl-assistant-dapr-peers", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = "pl-assistant" } }
      action   = "ALLOW"
      rules = [{
        from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/pl-assistant"] } }]
        to   = [{ operation = { ports = ["50002"] } }]
      }]
    }
  })

  depends_on = [kubectl_manifest.strict_mtls]
}
