data "aws_caller_identity" "workloads" {}

locals {
  reference_bucket = "powerlifting-reference-documents-${data.aws_caller_identity.workloads.account_id}-${var.region}"
  aws_workload_accounts = setunion(setsubtract(toset(keys(local.services)), ["pl-calculations"]), toset([
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
  for_each = local.aws_workload_accounts
  name     = "nolift-${each.key}"
}

module "workload_aws" {
  for_each = local.aws_workload_accounts
  source   = "../modules/workload-aws"

  role_arn = data.aws_iam_role.workload[each.key].arn
  region   = var.region
}
