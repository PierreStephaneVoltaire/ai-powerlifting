output "agent_url" {
  value = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
}

output "discord_interactions_service" {
  description = "Cluster address for the Discord Interactions Endpoint; expose /interactions publicly through the root Cloudflare tunnel"
  value       = "http://pl-coach-discord.${var.namespace}.svc.cluster.local:8000/interactions"
}
