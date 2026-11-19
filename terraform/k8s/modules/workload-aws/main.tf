variable "region" {
  type = string
}

variable "role_arn" {
  type     = string
  nullable = true
}

variable "shared_secret_name" {
  type     = string
  nullable = true
}

locals {
  mount_path = "/secrets/aws"
  token_path = "web-identity-token"

  legacy_env = {
    AWS_SHARED_CREDENTIALS_FILE = "${local.mount_path}/credentials"
    AWS_CONFIG_FILE             = "${local.mount_path}/config"
  }

  identity_env = {
    AWS_ROLE_ARN                = var.role_arn
    AWS_WEB_IDENTITY_TOKEN_FILE = "${local.mount_path}/${local.token_path}"
    AWS_STS_REGIONAL_ENDPOINTS  = "regional"
    AWS_EC2_METADATA_DISABLED   = "true"
  }

  env = merge(
    var.role_arn == null ? (var.shared_secret_name == null ? {} : local.legacy_env) : local.identity_env,
    { AWS_REGION = var.region, AWS_DEFAULT_REGION = var.region },
  )
}

output "env" {
  value = local.env
}

output "mount_path" {
  value = local.mount_path
}

output "secret_names" {
  value = var.role_arn == null && var.shared_secret_name != null ? [var.shared_secret_name] : []
}

output "token_paths" {
  value = var.role_arn == null ? [] : [local.token_path]
}
