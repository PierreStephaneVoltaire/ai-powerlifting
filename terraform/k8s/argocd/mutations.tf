locals {
  hosts = { app = var.app_domain, auth = var.auth_domain, llm = var.llm_domain, argocd = var.argocd_domain }
  private_values = {
    app_domain             = var.app_domain
    auth_domain            = var.auth_domain
    llm_domain             = var.llm_domain
    region                 = var.region
    dataset_bucket         = var.dataset_bucket
    coach_dataset_bucket   = var.coach_inputs.dataset_bucket
    reference_bucket       = "powerlifting-reference-documents-${data.aws_caller_identity.current.account_id}-${var.region}"
    discord_operator_id    = var.coach_inputs.discord_operator_id
    operator_person        = var.coach_inputs.operator_person
    discord_persons        = var.coach_inputs.discord_persons
    coach_providers        = var.coach_inputs.coach_providers
    operation_ai           = var.coach_inputs.operation_ai
    job_token_public_key   = var.app_inputs.job_token_public_key
    mcp_aliases            = var.app_inputs.mcp_aliases
    llm_url                = "https://${var.llm_domain}"
    authorization_endpoint = "https://${var.auth_domain}/application/o/authorize/"
    token_endpoint         = "https://${var.auth_domain}/application/o/token/"
    userinfo_endpoint      = "https://${var.auth_domain}/application/o/userinfo/"
    litellm_checksum       = var.app_inputs.litellm_checksum
    reference_checksum     = var.app_inputs.reference_checksum
    tunnel_checksum        = var.network_inputs.tunnel_checksum
    litellm_image          = var.litellm_image
  }

  workload_patches = { for app, workloads in local.workloads : app => [
    for w in workloads : {
      target = { kind = "Deployment", name = w.name }
      patch = yamlencode({
        apiVersion = "apps/v1"
        kind       = "Deployment"
        metadata   = { name = w.name }
        spec = merge(w.home ? { replicas = var.coach_inputs.replicas } : {}, {
          template = {
            metadata = merge(
              w.aws ? { labels = { "nolift.io/aws-workload" = null } } : {},
              length(w.annotations) > 0 ? { annotations = { for k, v in w.annotations : k => local.private_values[v] } } : {}
            )
            spec = merge(
              w.home ? { nodeSelector = { "kubernetes.io/hostname" = var.coach_inputs.node_name } } : {},
              w.coach ? { imagePullSecrets = [{ "$patch" = "replace" }, { name = var.coach_inputs.image_pull_secret }] } : {},
              { containers = [for c in w.containers : merge(
                { name = c.name },
                can(regex(local.ecr_pattern, c.image)) ? { image = "${local.ecr}/${c.image}:latest" } : {},
                startswith(c.image, local.marker) ? { image = local.private_values[trimprefix(c.image, local.marker)] } : {},
                length(c.private_env) > 0 || (w.aws && c.aws_mount) ? {
                  env = [for name in distinct(concat(c.env, w.aws && c.aws_mount ? keys(module.workload_aws[w.sa].env) : [])) : merge(
                    { name = name },
                    contains(keys(c.private_env), name) ? { value = local.private_values[c.private_env[name]] } : {},
                    w.aws && c.aws_mount ? (contains(keys(module.workload_aws[w.sa].env), name) ? { value = module.workload_aws[w.sa].env[name] } : {}) : {}
                  )]
                } : {}
              )] }
            )
          }
        })
      })
    } if w.aws || w.home || w.coach || length(w.annotations) > 0 || anytrue([for c in w.containers : can(regex(local.ecr_pattern, c.image)) || startswith(c.image, local.marker) || length(c.private_env) > 0])
  ] }

  route_patches = { for app, routes in local.routes : app => [
    for name, host in routes : {
      target = { kind = "HTTPRoute", name = name }
      patch  = yamlencode([{ op = "replace", path = "/spec/hostnames", value = [local.hosts[host]] }])
    }
  ] }

  mutations = { for app in local.apps : app => concat(local.workload_patches[app], local.route_patches[app], local.policy_patches[app], local.waypoint_patches[app]) }
}
