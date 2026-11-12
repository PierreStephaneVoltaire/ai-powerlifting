locals {
  security_domains = ["analytics", "budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"]
  security_names   = concat(["pl-security", "pl-coach", "pl-coach-discord"], [for name in local.security_domains : "pl-${name}"])

  security_authorities = merge([for name in local.security_names : {
    for hostname in [name, "${name}.${var.namespace}", "${name}.${var.namespace}.svc", "${name}.${var.namespace}.svc.cluster.local"] : hostname => name
  }]...)

  cache_callers = {
    "pl-valkey" = concat(
      ["powerlifting-app-backend", "oauth2-proxy", "pl-analytics", "pl-coach"],
      [for name in ["budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "pl-${name}"],
    )
    "pl-prompt-cache"     = ["pl-prompt-cache-mcp"]
    "pl-prompt-cache-mcp" = ["pl-coach"]
  }

  mesh_services = merge(
    {
      pl-security  = { service = "pl-security", app = "pl-security", port = 8000 }
      pl-analytics = { service = "pl-analytics", app = "pl-analytics", port = 8000 }
    },
    { for name, service in kubernetes_service_v1.service : service.metadata[0].name => { service = service.metadata[0].name, app = service.spec[0].selector.app, port = 8000 } },
  )

  edge_only_services = {
    "powerlifting-app-frontend" = { selector = { app = "powerlifting-app-frontend" }, port = 3001, caller = "edge-powerlifting" }
    "oauth2-proxy"              = { selector = { app = "oauth2-proxy" }, port = 4180, caller = "edge-powerlifting" }
    "edge-powerlifting"         = { selector = { "gateway.networking.k8s.io/gateway-name" = "edge" }, port = 80, caller = "cloudflared" }
  }
}

resource "kubectl_manifest" "cache_l4" {
  for_each = local.cache_callers

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-authorized-callers", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = each.key } }
      action   = "ALLOW"
      rules = [{
        from = [{ source = { principals = [for caller in each.value : "cluster.local/ns/${var.namespace}/sa/${caller}"] } }]
        to   = [{ operation = { ports = [{ "pl-valkey" = "6379", "pl-prompt-cache" = "6333", "pl-prompt-cache-mcp" = "8000" }[each.key]] } }]
      }]
    }
  })

  depends_on = [kubectl_manifest.strict_mtls]
}

resource "kubectl_manifest" "portal_waypoint" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "Gateway"
    metadata   = { name = "nolift-waypoint", namespace = var.namespace, labels = { "istio.io/waypoint-for" = "service" } }
    spec = {
      gatewayClassName = "istio-waypoint"
      listeners        = [{ name = "mesh", port = 15008, protocol = "HBONE" }]
    }
  })
}

resource "kubectl_manifest" "strict_mtls" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "PeerAuthentication"
    metadata   = { name = "powerlifting-strict-mtls", namespace = var.namespace }
    spec       = { mtls = { mode = "STRICT" } }
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

  depends_on = [kubectl_manifest.portal_waypoint, kubectl_manifest.strict_mtls, kubernetes_service_v1.service, kubernetes_service_v1.analytics, kubernetes_service_v1.security]
}

resource "kubectl_manifest" "edge_only" {
  for_each = local.edge_only_services

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-edge-only", namespace = var.namespace }
    spec = {
      selector = { matchLabels = each.value.selector }
      action   = "ALLOW"
      rules    = [{ from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/${each.value.caller}"] } }], to = [{ operation = { ports = [tostring(each.value.port)] } }] }]
    }
  })

  depends_on = [kubectl_manifest.strict_mtls]
}

resource "kubectl_manifest" "backend_from_oauth2_proxy" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "powerlifting-app-backend-oauth2-proxy-only", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = "powerlifting-app-backend" } }
      action   = "ALLOW"
      rules    = [{ from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/oauth2-proxy"] } }], to = [{ operation = { ports = ["3005"] } }] }]
    }
  })

  depends_on = [kubectl_manifest.strict_mtls, kubernetes_service_v1.backend]
}

resource "kubectl_manifest" "central_authz" {
  for_each = local.mesh_services

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-security-check", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.value.service }]
      action     = "CUSTOM"
      provider   = { name = "nolift-security" }
      rules      = [{ to = [{ operation = { ports = [tostring(each.value.port)] } }] }]
    }
  })

  depends_on = [kubectl_manifest.portal_waypoint, kubectl_manifest.strict_mtls, kubernetes_service_v1.service, kubernetes_service_v1.analytics, kubernetes_service_v1.security]
}

resource "kubectl_manifest" "authorized_destination" {
  for_each = local.mesh_services

  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "${each.key}-authorized-destination", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = each.value.service }]
      action     = "ALLOW"
      rules = [{
        when = [{ key = "request.headers[x-pl-authorized-destination]", values = [each.key] }]
        to   = [{ operation = { ports = [tostring(each.value.port)] } }]
      }]
    }
  })

  depends_on = [kubectl_manifest.central_authz, kubectl_manifest.strict_mtls]
}
