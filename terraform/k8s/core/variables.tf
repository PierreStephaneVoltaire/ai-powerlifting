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

variable "cookie_domain" {
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
