output "gateway_service_url" {
  value = "http://${local.gateway_service}.${var.namespace}.svc.cluster.local:80"
}

output "manifest_inputs" {
  sensitive = true
  value     = { tunnel_checksum = sha256(data.kubernetes_secret_v1.tunnel.data["token"]) }
}
