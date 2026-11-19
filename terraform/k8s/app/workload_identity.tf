variable "aws_workload_identity" {
  description = "App service accounts migrated to AWS workload identity."
  type        = set(string)
  default     = []
}

locals {
  credentialless_accounts = toset(["pl-calculations"])
  aws_workload_accounts = setunion(toset(keys(local.services)), toset([
    "ecr-refresher",
    "pl-analytics",
    "pl-analytics-ai",
    "pl-analytics-export",
    "pl-assistant",
    "pl-competition",
    "pl-glossary",
    "pl-profile",
    "pl-program",
    "pl-rankings",
    "pl-sessions",
    "powerlifting-app-backend",
  ]))
}

data "aws_iam_role" "workload" {
  for_each = var.aws_workload_identity
  name     = "nolift-${each.key}"

  lifecycle {
    precondition {
      condition     = contains(setsubtract(local.aws_workload_accounts, local.credentialless_accounts), each.key)
      error_message = "Unknown or credentialless App service account: ${each.key}."
    }
  }
}

module "workload_aws" {
  for_each = local.aws_workload_accounts
  source   = "../modules/workload-aws"

  role_arn           = try(data.aws_iam_role.workload[each.key].arn, null)
  region             = var.region
  shared_secret_name = contains(local.credentialless_accounts, each.key) ? null : "pl-aws-credentials"
}
