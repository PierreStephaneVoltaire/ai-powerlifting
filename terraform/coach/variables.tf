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

variable "aws_credentials_secret_name" {
  description = "Secret holding the AWS credentials and config files the Discord bot uses to read its registrations"
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

variable "coach_providers" {
  description = "Model providers Codex can run against. auth is chatgpt (subscription login) or api_key (base_url plus a key in coach_provider_api_keys); max_concurrent is that provider's concurrency limit"
  type = map(object({
    auth           = string
    max_concurrent = number
    base_url       = optional(string)
  }))
}

variable "coach_provider_api_keys" {
  description = "API key for each api_key provider"
  type        = map(string)
  sensitive   = true
}

variable "conversation_ai" {
  description = "Provider, model and reasoning effort for conversation turns (Discord chat, session notes, auto-regulation)"
  type = object({
    provider = string
    model    = string
    effort   = string
  })
}

variable "operation_ai" {
  description = "Provider, model and reasoning effort for each AI operation; the Coach refuses to start if an AI operation is missing"
  type = map(object({
    provider = string
    model    = string
    effort   = string
  }))
}

variable "coach_replicas" {
  description = "Coach pods; must be 1 while any provider uses the ChatGPT subscription login"
  type        = number
}
