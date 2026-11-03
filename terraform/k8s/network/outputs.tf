output "gateway_service_url" {
  value = "http://${local.gateway_service}.${var.namespace}.svc.cluster.local:80"
}
