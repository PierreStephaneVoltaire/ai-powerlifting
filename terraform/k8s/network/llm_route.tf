resource "kubectl_manifest" "llm_headers" {
  yaml_body = yamlencode({
    apiVersion = "gateway.nginx.org/v1alpha1"
    kind       = "SnippetsFilter"
    metadata   = { name = "llm-headers", namespace = var.namespace }
    spec = {
      snippets = [{
        context = "http.server.location"
        value   = <<-NGINX
          proxy_set_header X-Forwarded-Proto https;
          proxy_set_header X-PL-Source-Principal "";
          proxy_set_header X-Internal-Api-Token "";
          proxy_read_timeout 900s;
          proxy_buffering off;
          proxy_buffer_size 64k;
          proxy_buffers 8 64k;
          proxy_busy_buffers_size 128k;
          client_max_body_size 50M;
          add_header X-Content-Type-Options "nosniff" always;
          add_header Strict-Transport-Security "max-age=31536000; includeSubDomains" always;
        NGINX
      }]
    }
  })

  depends_on = [helm_release.gateway_controller]
}

resource "kubectl_manifest" "llm_route" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "HTTPRoute"
    metadata   = { name = "litellm", namespace = var.namespace }
    spec = {
      parentRefs = [{ name = local.gateway_name }]
      hostnames  = [var.llm_domain]
      rules = [{
        matches = [{ path = { type = "PathPrefix", value = "/" } }]
        filters = [{
          type         = "ExtensionRef"
          extensionRef = { group = "gateway.nginx.org", kind = "SnippetsFilter", name = "llm-headers" }
        }]
        backendRefs = [{ name = "litellm", port = 4000 }]
      }]
    }
  })

  depends_on = [kubectl_manifest.gateway, kubectl_manifest.llm_headers]
}
