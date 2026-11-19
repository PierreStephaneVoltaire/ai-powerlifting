variable "region" {
  type = string
}

variable "role_arn" {
  type     = string
  nullable = false
}

locals {
  mount_path = "/secrets/aws"
  token_path = "web-identity-token"
}

output "env" {
  value = {
    AWS_ROLE_ARN                = var.role_arn
    AWS_WEB_IDENTITY_TOKEN_FILE = "${local.mount_path}/${local.token_path}"
    AWS_STS_REGIONAL_ENDPOINTS  = "regional"
    AWS_EC2_METADATA_DISABLED   = "true"
    AWS_REGION                  = var.region
    AWS_DEFAULT_REGION          = var.region
  }
}

output "mount_path" {
  value = local.mount_path
}

output "token_path" {
  value = local.token_path
}
