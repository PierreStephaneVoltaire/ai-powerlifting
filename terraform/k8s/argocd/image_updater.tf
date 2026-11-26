resource "kubectl_manifest" "image_updater" {
  for_each = local.apps
  yaml_body = yamlencode({
    apiVersion = "argocd-image-updater.argoproj.io/v1alpha1"
    kind       = "ImageUpdater"
    metadata   = { name = "nolift-${each.key}", namespace = "argocd" }
    spec = {
      writeBackConfig = { method = "argocd" }
      applicationRefs = [{
        namePattern    = "nolift-${each.key}"
        useAnnotations = length(local.ecr_repos[each.key]) == 0
        images = [for repo in local.ecr_repos[each.key] : {
          alias                = trimprefix(repo, "if-")
          imageName            = "${local.ecr}/${repo}:latest"
          commonUpdateSettings = { updateStrategy = "digest", forceUpdate = true }
          manifestTargets      = { kustomize = { name = "${local.ecr}/${repo}" } }
        }]
      }]
    }
  })
  depends_on = [helm_release.argocd_image_updater, kubectl_manifest.application]
}
