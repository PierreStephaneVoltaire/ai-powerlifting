resource "kubectl_manifest" "l4_waypoint_only" {
  for_each = toset(["pl-coach", "pl-coach-discord"])

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-waypoint-only", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = each.key } }
      action   = "ALLOW"
      rules    = [{ from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/nolift-waypoint"] } }] }]
    }
  })
}

resource "kubectl_manifest" "central_authz" {
  for_each = toset(["pl-coach", "pl-coach-discord"])

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-security-check", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.key }]
      action     = "CUSTOM"
      provider   = { name = "nolift-security" }
      rules      = [{ to = [{ operation = { ports = ["8000"] } }] }]
    }
  })

  depends_on = [kubernetes_service_v1.coach, kubernetes_service_v1.coach_discord]
}

resource "kubectl_manifest" "authorized_destination" {
  for_each = toset(["pl-coach", "pl-coach-discord"])

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-authorized-destination", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.key }]
      action     = "ALLOW"
      rules = [{
        when = [{ key = "request.headers[x-pl-authorized-destination]", values = [each.key] }]
        to   = [{ operation = { ports = ["8000"] } }]
      }]
    }
  })

  depends_on = [kubectl_manifest.central_authz]
}
