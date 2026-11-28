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

variable "workers_enabled" {
  type    = bool
  default = false
}
variable "home_lan_cidr" {
  type    = string
  default = null
}
variable "worker_azs" {
  type    = list(string)
  default = ["ca-central-1a", "ca-central-1b", "ca-central-1d"]
}
variable "worker_min" {
  type    = number
  default = 0
}
variable "worker_desired" {
  type    = number
  default = 0
}
variable "worker_max" {
  type    = number
  default = 3
}
variable "worker_instance_types" {
  type    = list(string)
  default = ["m6a.large", "m6i.large", "m5a.large", "m5.large", "m7a.large", "m7i.large"]
}
variable "worker_ami_ssm_parameter" {
  type    = string
  default = "/aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id"
}
variable "worker_root_volume_gib" {
  type    = number
  default = 40
}
variable "worker_spot_max_price" {
  type    = string
  default = null
}
