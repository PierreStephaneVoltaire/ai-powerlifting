mock_provider "kubernetes" {}
mock_provider "helm" {}

variables {
  region    = "us-east-1"
  namespace = "powerlifting"
}

run "visibility_disabled_by_default" {
  command = plan

  assert {
    condition     = !contains(keys(yamldecode(helm_release.istiod.values[0])), "meshConfig")
    error_message = "ServiceEntry visibility must be opt-in."
  }
}

run "visibility_scoped_to_portal_namespace" {
  command = plan

  variables {
    namespace_service_entry_visibility_enabled = true
  }

  assert {
    condition     = yamldecode(helm_release.istiod.values[0]).meshConfig.serviceEntryVisibility.defaultVisibility == "PUBLIC" && yamldecode(helm_release.istiod.values[0]).meshConfig.serviceEntryVisibility.policies[0].visibility == "NAMESPACE" && yamldecode(helm_release.istiod.values[0]).meshConfig.serviceEntryVisibility.policies[0].matchingRules[0].namespaceSelector.matchLabels["kubernetes.io/metadata.name"] == "powerlifting"
    error_message = "Only portal ServiceEntries should become namespace-scoped."
  }
}
