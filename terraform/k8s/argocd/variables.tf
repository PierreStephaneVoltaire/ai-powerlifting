terraform {
  required_version = ">= 1.15.0"
  backend "s3" {}
  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    kubectl    = { source = "alekc/kubectl", version = "~> 2.1" }
    helm       = { source = "hashicorp/helm", version = "~> 2.17" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
  }
}

provider "aws" {
  region = var.region
}

provider "helm" {
  kubernetes {}
}

variable "region" { type = string }
variable "namespace" {
  type = string
  validation {
    condition     = var.namespace == "powerlifting"
    error_message = "The NoLift AppProject owns resources in powerlifting."
  }
}
variable "argocd_domain" { type = string }
variable "auth_domain" { type = string }
variable "app_domain" { type = string }
variable "llm_domain" { type = string }
variable "dataset_bucket" { type = string }
variable "litellm_image" {
  type    = string
  default = "ghcr.io/berriai/litellm:v1.108.8"
}
variable "argocd_auto_sync" {
  type    = bool
  default = false
}
variable "argocd_client_secret" {
  type      = string
  sensitive = true
}
variable "kubernetes_api_cidrs" {
  type    = set(string)
  default = []
}
variable "app_inputs" {
  type = object({
    job_token_public_key = string
    mcp_aliases          = string
    litellm_checksum     = string
    reference_checksum   = string
    waypoint_callers     = set(string)
    ingress              = set(string)
    egress               = set(string)
  })
}
variable "coach_inputs" {
  sensitive = true
  type = object({
    node_name           = string
    image_pull_secret   = string
    replicas            = number
    coach_providers     = string
    operation_ai        = string
    discord_operator_id = string
    operator_person     = string
    discord_persons     = string
    dataset_bucket      = string
    ingress             = set(string)
    egress              = set(string)
  })
}
variable "network_inputs" {
  type = object({ tunnel_checksum = string })
}

variable "argocd_cookie_migrated" {
  type    = bool
  default = false
}
