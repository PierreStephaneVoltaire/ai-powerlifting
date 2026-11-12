locals {
  coach_operations = flatten([for filename in fileset("${path.module}/../../src/services/operations", "*.json") : jsondecode(file("${path.module}/../../src/services/operations/${filename}"))])
  coach_callers = {
    "pl-coach"         = concat(["powerlifting-app-backend", "pl-coach-discord", "pl-analytics"], [for domain in toset([for operation in local.coach_operations : operation.domain if try(operation.execution, "") == "ai"]) : "pl-${domain}"])
    "pl-coach-discord" = ["powerlifting-app-backend"]
  }
}

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

resource "kubectl_manifest" "service_callers" {
  for_each = local.coach_callers

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-allowed-callers", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.key }]
      action     = "ALLOW"
      rules = [{
        from = [{ source = { principals = [for caller in each.value : "cluster.local/ns/${var.namespace}/sa/${caller}"] } }]
        to   = [{ operation = { ports = ["8000"] } }]
      }]
    }
  })

  depends_on = [kubernetes_service_v1.coach, kubernetes_service_v1.coach_discord]
}
