resource "null_resource" "gateway_api_crds" {
  provisioner "local-exec" {
    command = <<-EOT
      kubectl apply --server-side -k github.com/kubernetes-sigs/gateway-api/config/crd?ref=v1.2.0
    EOT
  }
}

resource "null_resource" "nginx_gateway_fabric_crds" {
  provisioner "local-exec" {
    command = <<-EOT
      helm pull oci://ghcr.io/nginx/charts/nginx-gateway-fabric --version 2.6.3 --untar --untardir /tmp/ngf-crd-install && \
      kubectl apply --server-side --force-conflicts -R -f /tmp/ngf-crd-install/nginx-gateway-fabric/crds/ && \
      rm -rf /tmp/ngf-crd-install
    EOT
  }

  depends_on = [null_resource.gateway_api_crds]
}

resource "kubernetes_namespace" "nginx_gateway" {
  metadata {
    name = "nginx-gateway"
    labels = {
      app        = "nginx-gateway-fabric"
      managed-by = "terraform"
    }
  }
}

resource "helm_release" "nginx_gateway_fabric" {
  name       = "ngf"
  namespace  = kubernetes_namespace.nginx_gateway.metadata[0].name
  repository = "oci://ghcr.io/nginx/charts"
  chart      = "nginx-gateway-fabric"
  version    = "2.6.3"

  set {
    name  = "nginx.service.type"
    value = "LoadBalancer"
  }

  set {
    name  = "nginxGateway.replicas"
    value = "2"
  }
  set {
    name  = "nginxGateway.snippets.enable"
    value = "true"
  }
  set {
    name  = "nginxGateway.resources.requests.memory"
    value = "128Mi"
  }
  set {
    name  = "nginxGateway.resources.limits.memory"
    value = "512Mi"
  }
  set {
    name  = "nginxGateway.resources.requests.cpu"
    value = "100m"
  }

  depends_on = [null_resource.gateway_api_crds, null_resource.nginx_gateway_fabric_crds]
}



resource "kubectl_manifest" "gateway" {
  depends_on = [helm_release.nginx_gateway_fabric]

  yaml_body = <<-YAML
apiVersion: gateway.networking.k8s.io/v1
kind: Gateway
metadata:
  name: ${var.gateway_name}
  namespace: ${var.gateway_namespace}
spec:
  gatewayClassName: nginx
  listeners:
    - name: http
      port: 80
      protocol: HTTP
      allowedRoutes:
        namespaces:
          from: All
  YAML
}
