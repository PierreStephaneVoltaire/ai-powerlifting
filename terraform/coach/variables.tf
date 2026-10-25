variable "region" {
  type = string
}

variable "kubeconfig_path" {
  type = string
}

variable "kubeconfig_context" {
  type     = string
  nullable = true
}

variable "namespace" {
  description = "Namespace shared with the Powerlifting Services"
  type        = string
}

variable "node_name" {
  description = "Node that holds the local-path Coach state volume"
  type        = string
  sensitive   = true
}

variable "image_pull_secret" {
  type = string
}

variable "shared_secret_name" {
  description = "Secret holding INTERNAL_API_TOKEN and PL_PRINCIPAL_SECRET for the Powerlifting Services"
  type        = string
}

variable "discord_secret_name" {
  description = "Secret holding the Discord bot token under DISCORD_TOKEN"
  type        = string
}

variable "discord_operator_id" {
  description = "Discord user id of the Operator"
  type        = string
  sensitive   = true
}

variable "operator_person" {
  type      = string
  sensitive = true
}

variable "discord_persons" {
  description = "Extra Discord user id to Person mappings"
  type        = map(string)
  sensitive   = true
}

variable "coach_model" {
  type = string
}

variable "coach_reasoning_effort" {
  type = string
}
