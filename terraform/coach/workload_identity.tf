data "aws_iam_role" "workload" {
  for_each = toset(["pl-coach", "pl-coach-discord"])
  name     = "nolift-${each.key}"
}

module "workload_aws" {
  for_each = data.aws_iam_role.workload
  source   = "../k8s/modules/workload-aws"

  role_arn = each.value.arn
  region   = var.region
}
