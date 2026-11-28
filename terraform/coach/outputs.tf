output "discord_interactions_service" {
  description = "Cluster address for the Discord Interactions Endpoint; expose /interactions publicly through the root Cloudflare tunnel"
  value       = "http://pl-coach-discord.${var.namespace}.svc.cluster.local:8000/interactions"
}

output "manifest_inputs" {
  sensitive = true
  value = {
    image_pull_secret   = var.image_pull_secret
    discord_operator_id = var.discord_operator_id
    operator_person     = var.operator_person
    discord_persons     = jsonencode(var.discord_persons)
    ingress             = var.network_policy_ingress_workloads
    egress              = var.network_policy_egress_workloads
  }
}
