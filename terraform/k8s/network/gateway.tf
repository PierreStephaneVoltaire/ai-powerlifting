locals {
  gateway_class   = "powerlifting"
  gateway_name    = "edge"
  gateway_service = "${local.gateway_name}-${local.gateway_class}"
}

data "http" "gateway_api_crds" {
  url = "https://github.com/kubernetes-sigs/gateway-api/releases/download/v1.2.0/standard-install.yaml"
}

data "kubectl_file_documents" "gateway_api_crds" {
  content = data.http.gateway_api_crds.response_body
}

resource "kubectl_manifest" "gateway_api_crds" {
  for_each = data.kubectl_file_documents.gateway_api_crds.manifests

  yaml_body         = each.value
  server_side_apply = true
  force_conflicts   = true
  wait              = true
}

resource "helm_release" "gateway_controller" {
  name       = "gateway"
  namespace  = var.namespace
  repository = "oci://ghcr.io/nginx/charts"
  chart      = "nginx-gateway-fabric"
  version    = "2.6.3"

  values = [yamlencode({
    nginxGateway = {
      replicas              = 1
      gatewayClassName      = local.gateway_class
      gatewayControllerName = "gateway.nginx.org/${local.gateway_class}-controller"
      watchNamespaces       = distinct([var.namespace, var.auth_namespace])
      snippets              = { enable = true }
    }
    nginx = {
      service = { type = "ClusterIP" }
    }
  })]

  depends_on = [kubectl_manifest.gateway_api_crds]

}

resource "kubectl_manifest" "gateway" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1"
    kind       = "Gateway"
    metadata   = { name = local.gateway_name, namespace = var.namespace }
    spec = {
      gatewayClassName = local.gateway_class
      infrastructure = {
        labels = { "istio.io/dataplane-mode" = "ambient" }
        parametersRef = {
          group = "gateway.nginx.org"
          kind  = "NginxProxy"
          name  = "edge-mesh-proxy"
        }
      }
      listeners = [{
        name          = "http"
        port          = 80
        protocol      = "HTTP"
        allowedRoutes = { namespaces = { from = "Same" } }
      }]
    }
  })

  depends_on = [helm_release.gateway_controller, kubectl_manifest.nginx_mesh_proxy]
}

resource "kubectl_manifest" "nginx_mesh_proxy" {
  yaml_body = yamlencode({
    apiVersion = "gateway.nginx.org/v1alpha2"
    kind       = "NginxProxy"
    metadata   = { name = "edge-mesh-proxy", namespace = var.namespace }
    spec       = { useClusterIP = true }
  })

  depends_on = [helm_release.gateway_controller]
}

resource "kubectl_manifest" "authentik_route_reference" {
  yaml_body = yamlencode({
    apiVersion = "gateway.networking.k8s.io/v1beta1"
    kind       = "ReferenceGrant"
    metadata   = { name = "authentik-gateway-route", namespace = var.auth_namespace }
    spec = {
      from = [{ group = "gateway.networking.k8s.io", kind = "HTTPRoute", namespace = var.namespace }]
      to   = [{ group = "", kind = "Service", name = "authentik-server" }]
    }
  })

  depends_on = [kubectl_manifest.gateway_api_crds]
}
