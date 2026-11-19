mock_provider "aws" {
  mock_data "aws_iam_role" {
    override_during = plan
    defaults        = { arn = "arn:aws:iam::429310424269:role/nolift-pl-rankings" }
  }

  mock_data "aws_ssm_parameters_by_path" {
    override_during = plan
    defaults = {
      names  = ["/powerlifting/litellm/provider_keys/openrouter"]
      values = ["mock"]
    }
  }
}

mock_provider "kubernetes" {
  mock_data "kubernetes_secret_v1" {
    override_during = plan
    defaults        = { data = { AUTHENTIK_CLIENT_SECRET = "mock" } }
  }
}
mock_provider "kubectl" {}
mock_provider "random" {}
mock_provider "tls" {}

variables {
  region         = "ca-central-1"
  namespace      = "powerlifting"
  storage_class  = "local-path"
  dataset_bucket = "powerlifting-data-2b0f699b"
  app_domain     = "app.example.com"
  auth_domain    = "auth.example.com"
  llm_domain     = "llm.example.com"
  repositories = {
    services         = "services"
    analytics        = "analytics"
    rankings         = "rankings"
    analytics_ai     = "analytics-ai"
    prompt_cache_api = "prompt-cache-api"
    analytics_export = "analytics-export"
    glossary         = "glossary"
    backend          = "backend"
    frontend         = "frontend"
  }
  litellm_providers = { openrouter = { type = "openrouter" } }
  litellm_models = {
    pl-strong = [{ provider = "openrouter", model = "test" }]
    pl-embed  = [{ provider = "openrouter", model = "test" }]
  }
}

run "rankings_canary" {
  command = plan

  variables {
    aws_workload_identity            = ["pl-rankings"]
    network_policy_ingress_workloads = ["pl-rankings"]
    network_policy_egress_workloads  = ["pl-rankings"]
    external_service_entries_enabled = true
    waypoint_network_policy_enabled  = true
  }

  assert {
    condition = one([
      for volume in kubernetes_deployment_v1.rankings.spec[0].template[0].spec[0].volume :
      one(volume.projected[0].sources).service_account_token[0].audience if volume.name == "aws"
    ]) == "sts.amazonaws.com"
    error_message = "Rankings must project an STS-only token."
  }

  assert {
    condition = alltrue([
      for rule in yamldecode(kubectl_manifest.workload_network_policy["pl-rankings"].yaml_body).spec.egress :
      alltrue([for peer in rule.to : !can(peer.ipBlock)])
    ])
    error_message = "Rankings must have no direct internet egress."
  }

  assert {
    condition     = yamldecode(kubectl_manifest.workload_network_policy["pl-rankings"].yaml_body).spec.ingress[0].from[0].podSelector.matchLabels["gateway.networking.k8s.io/gateway-name"] == "nolift-waypoint"
    error_message = "Rankings' Ambient traffic must come from the NoLift waypoint."
  }
}
