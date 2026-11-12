resource "kubectl_manifest" "edge_headers" {
  yaml_body = yamlencode({
    apiVersion = "gateway.nginx.org/v1alpha1"
    kind       = "SnippetsFilter"
    metadata   = { name = "edge-headers", namespace = var.namespace }
    spec = {
      snippets = [{
        context = "http.server.location"
        value   = <<-NGINX
          proxy_set_header X-Forwarded-Proto https;
          proxy_set_header Authorization "";
          proxy_set_header X-PL-Principal "";
          proxy_set_header X-PL-Mesh-Caller "";
          proxy_set_header X-PL-Access-Context "";
          proxy_set_header X-PL-Authorized-Destination "";
          proxy_set_header X-Internal-Api-Token "";
          proxy_read_timeout 300s;
          client_max_body_size 500M;
          add_header X-Frame-Options "SAMEORIGIN" always;
          add_header X-Content-Type-Options "nosniff" always;
          add_header Referrer-Policy "strict-origin-when-cross-origin" always;
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        NGINX
      }]
    }
  })

  depends_on = [helm_release.gateway_controller]
}

locals {
  edge_filter = [{
    type         = "ExtensionRef"
    extensionRef = { group = "gateway.nginx.org", kind = "SnippetsFilter", name = "edge-headers" }
  }]
}

resource "kubectl_manifest" "app_route" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "HTTPRoute"
    metadata   = { name = "powerlifting-app", namespace = var.namespace }
    spec = {
      parentRefs = [{ name = local.gateway_name }]
      hostnames  = [var.app_domain]
      rules = [
        {
          matches     = [{ path = { type = "PathPrefix", value = "/oauth2" } }]
          filters     = local.edge_filter
          backendRefs = [{ name = "oauth2-proxy", port = 4180 }]
        },
        {
          matches     = [{ path = { type = "PathPrefix", value = "/api" } }]
          filters     = local.edge_filter
          backendRefs = [{ name = "oauth2-proxy", port = 4180 }]
        },
        {
          matches     = [{ path = { type = "PathPrefix", value = "/" } }]
          filters     = local.edge_filter
          backendRefs = [{ name = "powerlifting-app-frontend", port = 3001 }]
        },
      ]
    }
  })

  depends_on = [kubectl_manifest.gateway, kubectl_manifest.edge_headers]
}

resource "kubectl_manifest" "auth_route" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "HTTPRoute"
    metadata   = { name = "authentik", namespace = var.namespace }
    spec = {
      parentRefs = [{ name = local.gateway_name }]
      hostnames  = [var.auth_domain]
      rules = [{
        filters = [{
          type = "RequestHeaderModifier"
          requestHeaderModifier = {
            set = [{ name = "X-Forwarded-Proto", value = "https" }]
          }
        }]
        backendRefs = [{ name = "authentik-server", namespace = var.auth_namespace, port = 80 }]
      }]
    }
  })

  depends_on = [kubectl_manifest.gateway, kubectl_manifest.authentik_route_reference]
}
