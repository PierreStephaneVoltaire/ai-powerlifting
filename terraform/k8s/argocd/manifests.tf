data "aws_caller_identity" "current" {}

locals {
  deploy_root = "${path.module}/../../../deploy/argocd"
  apps        = toset(["app", "coach", "network"])
  repo        = "https://github.com/PierreStephaneVoltaire/ai-powerlifting.git"
  ecr         = "${data.aws_caller_identity.current.account_id}.dkr.ecr.${var.region}.amazonaws.com"
  ecr_pattern = "^if-[a-z0-9-]+$"
  marker      = "nolift:private:"

  docs = { for app in local.apps : app => flatten([
    for name in fileset("${local.deploy_root}/${app}", "*.yaml") : [
      for doc in split("\n---\n", file("${local.deploy_root}/${app}/${name}")) : yamldecode(doc)
      if trimspace(doc) != ""
    ] if name != "kustomization.yaml"
  ]) }
  workloads = { for app, docs in local.docs : app => [
    for d in docs : {
      name        = d.metadata.name
      sa          = try(d.spec.template.spec.serviceAccountName, "default")
      aws         = try(d.spec.template.metadata.labels["nolift.io/aws-workload"] == "true", false)
      home        = try(d.metadata.annotations["nolift.io/home-node"] == "true", false)
      coach       = try(d.metadata.annotations["nolift.io/coach-settings"] == "true", false)
      annotations = { for key, value in try(d.spec.template.metadata.annotations, {}) : key => trimprefix(value, local.marker) if startswith(value, local.marker) }
      containers = [for c in d.spec.template.spec.containers : {
        name        = c.name
        image       = c.image
        env         = [for e in try(c.env, []) : e.name]
        private_env = { for e in try(c.env, []) : e.name => trimprefix(e.value, local.marker) if startswith(try(e.value, ""), local.marker) }
        aws_mount   = contains([for m in try(c.volumeMounts, []) : m.mountPath], "/secrets/aws")
      }]
    } if d.kind == "Deployment"
  ] }
  aws_accounts = toset(flatten([for workloads in values(local.workloads) : [for w in workloads : w.sa if w.aws]]))
  ecr_repos    = { for app, workloads in local.workloads : app => toset(flatten([for w in workloads : [for c in w.containers : c.image if can(regex(local.ecr_pattern, c.image))]])) }
  routes       = { for app, docs in local.docs : app => { for d in docs : d.metadata.name => d.metadata.annotations["nolift.io/hostname"] if d.kind == "HTTPRoute" } }
  policy_docs  = { for app, docs in local.docs : app => [for d in docs : d if can(d.metadata.annotations["nolift.io/isolation"])] }
  placeholder_keys = { for app, docs in local.docs : app => toset(flatten([
    for doc in docs : regexall("nolift:private:([a-zA-Z0-9_]+)", jsonencode(doc))
  ])) }
}

data "aws_iam_role" "workload" {
  for_each = local.aws_accounts
  name     = "nolift-${each.key}"
}

module "workload_aws" {
  source   = "../modules/workload-aws"
  for_each = local.aws_accounts
  role_arn = data.aws_iam_role.workload[each.key].arn
  region   = var.region
}
