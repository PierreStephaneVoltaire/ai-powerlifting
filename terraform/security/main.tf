terraform {
  required_version = ">= 1.11.0"

  backend "s3" {}

  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 6.0" }
    tls = { source = "hashicorp/tls", version = "~> 4.1" }
  }
}

variable "region" {
  type    = string
  default = "ca-central-1"
}

provider "aws" {
  region = var.region
}

data "aws_ssm_parameters_by_path" "security" {
  path            = "/powerlifting/security/"
  recursive       = false
  with_decryption = false
}

locals {
  parameters = {
    private = { name = "/powerlifting/security/principal-signing-private-key", type = "SecureString" }
    public  = { name = "/powerlifting/security/principal-signing-public-key", type = "String" }
  }
  existing = { for key, parameter in local.parameters : key => parameter if contains(data.aws_ssm_parameters_by_path.security.names, parameter.name) }
}

ephemeral "tls_private_key" "principal" {
  algorithm = "RSA"
  rsa_bits  = 3072
}

import {
  for_each = local.existing
  to       = aws_ssm_parameter.principal[each.key]
  id       = each.value.name
}

resource "aws_ssm_parameter" "principal" {
  for_each = local.parameters

  name             = each.value.name
  type             = each.value.type
  value_wo         = each.key == "private" ? ephemeral.tls_private_key.principal.private_key_pem : ephemeral.tls_private_key.principal.public_key_pem
  value_wo_version = 1

  lifecycle {
    prevent_destroy = true
    ignore_changes  = [value_wo_version]

    precondition {
      condition     = length(local.existing) == 0 || length(local.existing) == length(local.parameters)
      error_message = "Both signing-key parameters must exist together, or neither may exist."
    }
  }
}
