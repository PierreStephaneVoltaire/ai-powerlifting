data "aws_caller_identity" "workloads" {}

locals {
  reference_bucket = "powerlifting-reference-documents-${data.aws_caller_identity.workloads.account_id}-${var.region}"
  aws_workload_accounts = toset(concat(["ecr-refresher"], [for filename in fileset("${path.module}/../../../deploy/argocd/app", "*.yaml") : [
    for document in split("\n---\n", file("${path.module}/../../../deploy/argocd/app/${filename}")) : yamldecode(document).spec.template.spec.serviceAccountName
    if try(yamldecode(document).spec.template.metadata.labels["nolift.io/aws-workload"] == "true", false)
  ]]...))
}
data "aws_iam_role" "workload" {
  for_each = toset(["ecr-refresher"])
  name     = "nolift-${each.key}"
}

module "workload_aws" {
  for_each = toset(["ecr-refresher"])
  source   = "../modules/workload-aws"

  role_arn = data.aws_iam_role.workload[each.key].arn
  region   = var.region
}
