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

variable "auth_origin_url" {
  type = string
}
