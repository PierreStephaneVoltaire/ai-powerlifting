locals {
  mesh_destinations = merge(local.security_destinations, { "pl-backend" = 9021 })

  mesh_services = merge(
    {
      powerlifting-app-backend  = { service = "powerlifting-app-backend", app = "powerlifting-app-backend", port = 3005, destination = "pl-backend" }
      powerlifting-app-frontend = { service = "powerlifting-app-frontend", app = "powerlifting-app-frontend", port = 3001, destination = "pl-frontend" }
      oauth2-proxy              = { service = "oauth2-proxy", app = "oauth2-proxy", port = 4180, destination = "pl-oauth2-proxy" }
      pl-security               = { service = "pl-security", app = "pl-security", port = 8000, destination = "pl-security" }
      pl-analytics              = { service = "pl-analytics", app = "pl-analytics", port = 8000, destination = "pl-analytics" }
      pl-coach                  = { service = "pl-coach", app = "pl-coach", port = 8000, destination = "pl-coach" }
      pl-coach-discord          = { service = "pl-coach-discord", app = "pl-coach-discord", port = 8000, destination = "pl-coach-discord" }
    },
    { for name, service in kubernetes_service_v1.service : service.metadata[0].name => { service = service.metadata[0].name, app = service.spec[0].selector.app, port = 8000, destination = service.metadata[0].name } },
  )
}

resource "kubectl_manifest" "portal_waypoint" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "Gateway"
    metadata   = { name = "nolift-waypoint", namespace = var.namespace, labels = { "istio.io/waypoint-for" = "all" } }
    spec = {
      gatewayClassName = "istio-waypoint"
      listeners        = [{ name = "mesh", port = 15008, protocol = "HBONE" }]
    }
  })
}

resource "kubectl_manifest" "l4_waypoint_only" {
  for_each = local.mesh_services

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-waypoint-only", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = each.value.app } }
      action   = "ALLOW"
      rules    = [{ from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/nolift-waypoint"] } }] }]
    }
  })

  depends_on = [kubectl_manifest.portal_waypoint]
}

resource "kubectl_manifest" "central_authz" {
  for_each = { for key, value in local.mesh_services : key => value if !contains(["powerlifting-app-frontend", "oauth2-proxy"], key) }

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-security-check", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.value.service }]
      action     = "CUSTOM"
      provider   = { name = "nolift-${each.value.destination}" }
      rules      = [{ to = [{ operation = { ports = [tostring(each.value.port)] } }] }]
    }
  })

  depends_on = [kubectl_manifest.portal_waypoint]
}
