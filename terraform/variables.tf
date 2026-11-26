variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "powerlifting_s3_bucket" {
  type    = string
  default = "powerlifting-openpowerlifting-dataset"
}

variable "cloudflare_api_token" {
  type      = string
  sensitive = true
}

variable "cloudflare_account_id" {
  type = string
}

variable "tunnel_origin_url" {
  type = string
}

variable "app_domain" {
  type = string
}

variable "app_zone" {
  type = string
}

variable "cloudflare_zone_plan" {
  type = string
}

variable "auth_domain" {
  type = string
}

variable "argocd_domain" {
  type = string
  validation {
    condition     = endswith(var.argocd_domain, ".${var.app_zone}") && !contains([var.app_domain, var.auth_domain, var.llm_domain], var.argocd_domain)
    error_message = "Set argocd_domain to a distinct hostname in the portal's Cloudflare zone."
  }
}

variable "glossary_table_name" {
  type = string
}

variable "glossary_catalog_function_name" {
  type = string
}
