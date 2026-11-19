variable "aws_workload_identity" {
  description = "Coach service accounts migrated to AWS workload identity."
  type        = set(string)
  default     = []

  validation {
    condition     = length(setsubtract(var.aws_workload_identity, ["pl-coach", "pl-coach-discord"])) == 0
    error_message = "Only pl-coach and pl-coach-discord can be migrated in the Coach stack."
  }
}

data "aws_iam_role" "workload" {
  for_each = var.aws_workload_identity
  name     = "nolift-${each.key}"
}

module "workload_aws" {
  for_each = toset(["pl-coach", "pl-coach-discord"])
  source   = "../k8s/modules/workload-aws"

  role_arn           = try(data.aws_iam_role.workload[each.key].arn, null)
  region             = var.region
  shared_secret_name = var.aws_credentials_secret_name
}
