output "namespace" {
  value = kubernetes_namespace_v1.powerlifting.metadata[0].name
}

output "registry_server" {
  value = local.registry_server
}

output "runner_label" {
  value = helm_release.runner_scale_set.name
}

output "grafana_url" {
  value = "http://localhost:${kubernetes_service_v1.grafana.spec[0].port[0].port}"
}
