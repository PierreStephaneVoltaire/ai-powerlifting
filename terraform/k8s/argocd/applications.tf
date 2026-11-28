resource "kubectl_manifest" "project" {
  yaml_body = yamlencode({
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "AppProject"
    metadata   = { name = "nolift", namespace = "argocd" }
    spec = {
      sourceRepos              = [local.repo]
      destinations             = [{ server = "https://kubernetes.default.svc", namespace = var.namespace }]
      clusterResourceWhitelist = []
      namespaceResourceWhitelist = distinct(flatten([for docs in values(local.docs) : [
        for d in docs : { group = length(split("/", d.apiVersion)) == 1 ? "" : split("/", d.apiVersion)[0], kind = d.kind }
      ]]))
    }
  })
  depends_on = [helm_release.argocd]
}

resource "kubectl_manifest" "application" {
  for_each          = local.apps
  server_side_apply = true
  field_manager     = "terraform"
  yaml_body = yamlencode({
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata   = { name = "nolift-${each.key}", namespace = "argocd", annotations = { "argocd.argoproj.io/compare-options" = "ServerSideDiff=true" } }
    spec = {
      project     = "nolift"
      destination = { server = "https://kubernetes.default.svc", namespace = var.namespace }
      source = {
        repoURL        = local.repo
        targetRevision = var.argocd_target_revision
        path           = "deploy/argocd/${each.key}"
        kustomize      = { patches = local.mutations[each.key] }
      }
      syncPolicy = merge({
        syncOptions = ["ServerSideApply=true", "PruneLast=true", "ClientSideApplyMigration=false", "FailOnSharedResource=true"]
      }, var.argocd_auto_sync ? { automated = { prune = true, selfHeal = true } } : {})
    }
  })
  lifecycle {
    precondition {
      condition     = length(setsubtract(local.placeholder_keys[each.key], keys(local.private_values))) == 0
      error_message = "A Git manifest contains an unknown private marker."
    }
    precondition {
      condition = alltrue([for w in local.workloads[each.key] : !w.aws || (
        try(data.aws_iam_role.workload[w.sa].arn != "", false) && anytrue([for c in w.containers : c.aws_mount])
      )])
      error_message = "AWS workloads require their dedicated IAM role and mounted projected token."
    }
    precondition {
      condition     = alltrue([for d in local.docs[each.key] : d.metadata.namespace == var.namespace && !contains(["PersistentVolumeClaim", "Secret", "Namespace"], d.kind)])
      error_message = "The project may only adopt namespaced workload manifests."
    }
  }
  depends_on = [kubectl_manifest.project, kubectl_manifest.argocd_backend]
}
