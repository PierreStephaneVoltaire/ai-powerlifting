variable "region" {
  type = string
}

variable "namespace" {
  type = string
}

variable "app_domain" {
  type = string
}

variable "auth_domain" {
  type = string
}

variable "tables" {
  type = object({
    powerlifting        = string
    users               = string
    sessions            = string
    analysis_cache      = string
    master_competitions = string
    user_competitions   = string
    master_federations  = string
    user_federations    = string
    goals               = string
    budget              = string
  })
}

variable "budget_media_bucket" {
  type = string
}

variable "discord_client_id" {
  type = string
}

variable "discord_client_secret" {
  type      = string
  sensitive = true
}

variable "authentik_client_id" {
  type = string
}

variable "runner_namespace" {
  type = string
}

variable "runner_repository_url" {
  type = string
}

variable "runner_name" {
  type = string
}

variable "github_app_id" {
  type = string
}

variable "github_app_installation_id" {
  type = string
}

variable "github_app_private_key" {
  type      = string
  sensitive = true
}

variable "discord_bot_token" {
  type      = string
  sensitive = true
}
variable "authentik_bootstrap_email" {
  type = string
}

variable "authentik_bootstrap_password" {
  type      = string
  sensitive = true
}

variable "authentik_bootstrap_token" {
  type      = string
  sensitive = true
}

variable "storage_class" {
  type = string
}

variable "node_name" {
  type = string
}

variable "loki_storage_gb" {
  type = number
}

variable "prometheus_storage_gb" {
  type = number
}

variable "grafana_storage_gb" {
  type = number
}

variable "log_retention_days" {
  type = number
}

variable "metrics_retention_days" {
  type = number
}

variable "grafana_admin_password" {
  type      = string
  sensitive = true
}

variable "authentik_client_secret" {
  type      = string
  sensitive = true
}

variable "jwt_secret" {
  type      = string
  sensitive = true
}

variable "internal_api_token" {
  type      = string
  sensitive = true
}

variable "workout_videos_table" {
  type    = string
  default = "workout-Videos"
}
