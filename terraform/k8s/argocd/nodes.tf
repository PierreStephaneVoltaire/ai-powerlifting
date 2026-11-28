variable "workers_enabled" {
  type    = bool
  default = false
}
resource "kubectl_manifest" "nodes_project" {
  yaml_body = yamlencode({
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "AppProject"
    metadata   = { name = "nolift-nodes", namespace = "argocd" }
    spec = {
      sourceRepos = [local.repo]
      destinations = [
        { server = "https://kubernetes.default.svc", namespace = "kube-system" },
        { server = "https://kubernetes.default.svc", namespace = "cattle-system" }
      ]
      namespaceResourceWhitelist = [
        { group = "", kind = "ServiceAccount" },
        { group = "apps", kind = "Deployment" },
        { group = "batch", kind = "CronJob" },
        { group = "upgrade.cattle.io", kind = "Plan" }
      ]
      clusterResourceWhitelist = [
        { group = "rbac.authorization.k8s.io", kind = "ClusterRole" },
        { group = "rbac.authorization.k8s.io", kind = "ClusterRoleBinding" }
      ]
    }
  })
  depends_on = [helm_release.argocd]
}
resource "kubectl_manifest" "nodes_application" {
  count = var.workers_enabled ? 1 : 0
  yaml_body = yamlencode({
    apiVersion = "argoproj.io/v1alpha1"
    kind       = "Application"
    metadata   = { name = "nolift-nodes", namespace = "argocd" }
    spec = {
      project     = "nolift-nodes"
      destination = { server = "https://kubernetes.default.svc", namespace = "kube-system" }
      source      = { repoURL = local.repo, targetRevision = var.argocd_target_revision, path = "deploy/argocd/nodes" }
      syncPolicy  = { automated = { prune = true, selfHeal = true }, syncOptions = ["ServerSideApply=true", "PruneLast=true", "FailOnSharedResource=true"] }
    }
  })
  depends_on = [kubectl_manifest.nodes_project]
}
