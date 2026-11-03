locals {
  runner_service_account = "powerlifting-deployer"
}

resource "kubernetes_namespace_v1" "runner" {
  metadata {
    name = var.runner_namespace
  }

  lifecycle {
    ignore_changes = [metadata[0].annotations]
  }
}

resource "helm_release" "runner_controller" {
  name       = "arc"
  namespace  = kubernetes_namespace_v1.runner.metadata[0].name
  repository = "oci://ghcr.io/actions/actions-runner-controller-charts"
  chart      = "gha-runner-scale-set-controller"
  version    = "0.15.1"
}

resource "kubernetes_secret_v1" "runner_github_app" {
  metadata {
    name      = "github-app"
    namespace = kubernetes_namespace_v1.runner.metadata[0].name
  }

  data = {
    github_app_id              = var.github_app_id
    github_app_installation_id = var.github_app_installation_id
    github_app_private_key     = var.github_app_private_key
  }
}

resource "helm_release" "runner_scale_set" {
  name       = var.runner_name
  namespace  = kubernetes_namespace_v1.runner.metadata[0].name
  repository = "oci://ghcr.io/actions/actions-runner-controller-charts"
  chart      = "gha-runner-scale-set"
  version    = "0.15.1"

  values = [yamlencode({
    githubConfigUrl    = var.runner_repository_url
    githubConfigSecret = kubernetes_secret_v1.runner_github_app.metadata[0].name
    minRunners         = 0
    maxRunners         = 2
    controllerServiceAccount = {
      namespace = kubernetes_namespace_v1.runner.metadata[0].name
      name      = "arc-gha-rs-controller"
    }
    template = {
      spec = {
        serviceAccountName = local.runner_service_account
        containers = [{
          name    = "runner"
          image   = "ghcr.io/actions/actions-runner:latest"
          command = ["/home/runner/run.sh"]
        }]
      }
    }
  })]

  depends_on = [helm_release.runner_controller]
}
