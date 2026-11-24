resource "kubectl_manifest" "template_domain_calls" {
  for_each = {
    pl-glossary  = { caller = "pl-imports", operation = "exercise_upsert" }
    pl-goals     = { caller = "pl-templates", operation = "goals_list" }
    pl-program   = { caller = "pl-templates", operation = "block_transition" }
    pl-templates = { caller = "pl-imports", operation = "template_create_from_import" }
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

resource "kubectl_manifest" "export_glossary" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "pl-export-to-pl-glossary", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = "pl-glossary" }]
      action     = "ALLOW"
      rules = [{
        from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/pl-export"] } }]
        to   = [{ operation = { ports = ["8000"], methods = ["POST"], paths = ["/operations/exercise_get_glossary"] } }]
      }]
    }
  })
}
