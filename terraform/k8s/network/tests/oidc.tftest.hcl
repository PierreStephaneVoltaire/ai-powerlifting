mock_provider "helm" {}
mock_provider "http" {}
mock_provider "kubernetes" {
  mock_data "kubernetes_secret_v1" {
    defaults = { data = { token = "test-token" } }
  }
}
mock_provider "kubectl" {
  mock_data "kubectl_file_documents" {
    defaults = { manifests = {} }
  }
}

variables {
  namespace   = "powerlifting"
  app_domain  = "dev.nolift.training"
  auth_domain = "auth.nolift.training"
}

run "authentik_keeps_https_origin" {
  command = plan

  assert {
    condition = alltrue([
      for rule in yamldecode(kubectl_manifest.auth_route.yaml_body).spec.rules :
      anytrue([
        for filter in try(rule.filters, []) :
        filter.type == "RequestHeaderModifier" && try(contains(filter.requestHeaderModifier.set, {
          name = "X-Forwarded-Proto", value = "https"
        }), false)
      ])
    ])
    error_message = "Authentik must receive the public HTTPS scheme after TLS terminates at Cloudflare."
  }

  assert {
    condition = alltrue([
      for rule in yamldecode(kubectl_manifest.auth_route.yaml_body).spec.rules :
      alltrue([
        for filter in try(rule.filters, []) :
        filter.type != "ExtensionRef"
      ])
    ])
    error_message = "Authentik API requests must keep their Authorization header instead of using the application's header-stripping snippet."
  }
}
