resource "kubectl_manifest" "waypoint_source_principal" {
  yaml_body = yamlencode({
    apiVersion = "networking.istio.io/v1alpha3"
    kind       = "EnvoyFilter"
    metadata   = { name = "nolift-waypoint-source-principal", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "gateway.networking.k8s.io", kind = "Gateway", name = "nolift-waypoint" }]
      priority   = 10
      configPatches = [{
        applyTo = "HTTP_FILTER"
        patch = {
          operation = "INSERT_FIRST"
          value = {
            name = "envoy.filters.http.lua"
            typed_config = {
              "@type"    = "type.googleapis.com/envoy.extensions.filters.http.lua.v3.Lua"
              inlineCode = <<-LUA
                function envoy_on_request(request_handle)
                  local headers = request_handle:headers()
                  headers:remove("x-pl-source-principal")
                  local state = request_handle:streamInfo():filterState()
                  if not state then return end
                  local principal = state:get("io.istio.peer_principal")
                  if principal then headers:replace("x-pl-source-principal", principal) end
                end
              LUA
            }
          }
        }
      }]
    }
  })

  depends_on = [kubectl_manifest.portal_waypoint]
}
