mock_provider "aws" {
  mock_data "aws_caller_identity" {
    defaults = { account_id = "000000000000" }
  }
  mock_data "aws_iam_role" {
    defaults = { arn = "arn:aws:iam::000000000000:role/mock" }
  }
}
mock_provider "helm" {}
mock_provider "kubectl" {}
mock_provider "kubernetes" {}

variables {
  namespace            = "powerlifting"
  region               = "us-east-1"
  app_domain           = "app.example.invalid"
  auth_domain          = "auth.example.invalid"
  llm_domain           = "llm.example.invalid"
  argocd_domain        = "argo.example.invalid"
  argocd_client_secret = "fixture"
  dataset_bucket       = "fixture"
  kubernetes_api_cidrs = ["192.0.2.1/32"]
  app_inputs = {
    job_token_public_key = "fixture", mcp_aliases = "fixture", litellm_checksum = "fixture",
    reference_checksum   = "fixture", waypoint_callers = ["pl-assistant"], ingress = ["pl-rankings"], egress = ["pl-assistant"]
  }
  coach_inputs = {
    node_name       = "fixture", image_pull_secret = "ecr-registry", replicas = 1,
    coach_providers = "{}", operation_ai = "{}", discord_operator_id = "fixture",
    operator_person = "fixture", discord_persons = "{}", dataset_bucket = "fixture",
    ingress         = [], egress = []
  }
  network_inputs = { tunnel_checksum = "fixture" }
}

run "manual_adoption" {
  command = plan
  assert {
    condition = alltrue([for app in kubectl_manifest.application :
      !can(yamldecode(app.yaml_body).spec.source.kustomize.images) &&
      !can(yamldecode(app.yaml_body).spec.syncPolicy.automated)
    ])
    error_message = "Initial adoption needs manual sync and independently owned image overrides."
  }
  assert {
    condition = alltrue([for rule in one([for d in local.docs.network : d if d.kind == "HTTPRoute" && d.metadata.name == "authentik"]).spec.rules :
      anytrue([for f in rule.filters : try(contains(f.requestHeaderModifier.set, { name = "X-Forwarded-Proto", value = "https" }), false)]) &&
      alltrue([for f in rule.filters : f.type != "ExtensionRef"])
    ])
    error_message = "Authentik must retain its authorization header and receive the public HTTPS scheme."
  }
  assert {
    condition     = length(local.ecr_repos.coach) == 2 && length(local.ecr_repos.network) == 0 && contains(local.ecr_repos.app, "if-powerlifting-sessions")
    error_message = "Image Updaters must match the bare repositories declared in each source."
  }
  assert {
    condition = alltrue([for patch in local.policy_patches.app :
      patch.target.name == "pl-assistant-isolation" ? (
        yamldecode(patch.patch)[0].value.policyTypes == ["Egress"] &&
        strcontains(patch.patch, "192.0.2.1/32")
      ) : patch.target.name == "pl-rankings-isolation" ? yamldecode(patch.patch)[0].value.policyTypes == ["Ingress"] : yamldecode(patch.patch)["$patch"] == "delete"
    ])
    error_message = "Preserve the selected isolation directions and private API egress rules."
  }
  assert {
    condition     = yamldecode(kubectl_manifest.image_updater["network"].yaml_body).spec.applicationRefs[0].useAnnotations
    error_message = "An application with zero ECR repositories must satisfy the ImageUpdater CRD's empty-list validation."
  }
}

run "promote_digest_updates" {
  command = plan
  variables {
    argocd_auto_sync = true
  }
  assert {
    condition = alltrue([for app in kubectl_manifest.application :
      yamldecode(app.yaml_body).spec.syncPolicy.automated == { prune = true, selfHeal = true } &&
      !can(yamldecode(app.yaml_body).spec.source.kustomize.images)
    ])
    error_message = "Promotion must enable automatic sync while preserving independent image ownership."
  }
  assert {
    condition = yamldecode(helm_release.argocd_image_updater.values[0]).replicaCount == 1 && alltrue([
      for entry in yamldecode(kubectl_manifest.image_updater["app"].yaml_body).spec.applicationRefs[0].images :
      entry.commonUpdateSettings.updateStrategy == "digest" && endswith(entry.imageName, ":latest")
    ])
    error_message = "Image Updater must follow each latest digest after handoff."
  }
}
