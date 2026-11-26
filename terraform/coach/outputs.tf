output "agent_url" {
  value = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
}

output "discord_interactions_service" {
  description = "Cluster address for the Discord Interactions Endpoint; expose /interactions publicly through the root Cloudflare tunnel"
  value       = "http://pl-coach-discord.${var.namespace}.svc.cluster.local:8000/interactions"
}

output "manifest_inputs" {
  sensitive = true
  value = {
    node_name           = var.node_name
    image_pull_secret   = var.image_pull_secret
    replicas            = var.coach_replicas
    coach_providers     = jsonencode(var.coach_providers)
    operation_ai        = jsonencode(var.operation_ai)
    discord_operator_id = var.discord_operator_id
    operator_person     = var.operator_person
    discord_persons     = jsonencode(var.discord_persons)
    dataset_bucket      = var.dataset_bucket
    ingress             = var.network_policy_ingress_workloads
    egress              = var.network_policy_egress_workloads
  }
  precondition {
    condition     = var.coach_replicas == 1 || alltrue([for provider in values(var.coach_providers) : provider.auth != "chatgpt"])
    error_message = "ChatGPT subscription login requires one Coach replica."
  }
}
