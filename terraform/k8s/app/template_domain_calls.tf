resource "kubectl_manifest" "template_domain_calls" {
  for_each = {
    pl-glossary = { caller = "pl-imports", operation = "exercise_upsert" }
    pl-goals    = { caller = "pl-templates", operation = "goals_list" }
  }

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.value.caller}-to-${each.key}", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.key }]
      action     = "ALLOW"
      rules = [{
        from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/${each.value.caller}"] } }]
        to   = [{ operation = { ports = ["8000"], methods = ["POST"], paths = ["/operations/${each.value.operation}"] } }]
      }]
    }
  })
}
