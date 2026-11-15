resource "helm_release" "dapr" {
  name       = "dapr"
  repository = "https://dapr.github.io/helm-charts/"
  chart      = "dapr"
  version    = "1.16.21"
  namespace  = kubernetes_namespace_v1.dapr_system.metadata[0].name
  timeout    = 600

  set {
    name  = "global.ha.enabled"
    value = "false"
  }
  set {
    name  = "dapr_scheduler.enabled"
    value = "true"
  }
  set {
    name  = "dapr_placement.enabled"
    value = "true"
  }
  set {
    name  = "dapr_operator.resources.requests.cpu"
    value = "25m"
  }
  set {
    name  = "dapr_operator.resources.requests.memory"
    value = "64Mi"
  }
  set {
    name  = "dapr_operator.resources.limits.memory"
    value = "256Mi"
  }
  set {
    name  = "dapr_sentry.resources.requests.cpu"
    value = "25m"
  }
  set {
    name  = "dapr_sentry.resources.requests.memory"
    value = "64Mi"
  }
  set {
    name  = "dapr_sentry.resources.limits.memory"
    value = "256Mi"
  }
  set {
    name  = "dapr_sidecar_injector.resources.requests.cpu"
    value = "25m"
  }
  set {
    name  = "dapr_sidecar_injector.resources.requests.memory"
    value = "64Mi"
  }
  set {
    name  = "dapr_sidecar_injector.resources.limits.memory"
    value = "256Mi"
  }
  set {
    name  = "dapr_placement.resources.requests.cpu"
    value = "25m"
  }
  set {
    name  = "dapr_placement.resources.requests.memory"
    value = "64Mi"
  }
  set {
    name  = "dapr_placement.resources.limits.memory"
    value = "256Mi"
  }
  set {
    name  = "dapr_scheduler.resources.requests.cpu"
    value = "50m"
  }
  set {
    name  = "dapr_scheduler.resources.requests.memory"
    value = "128Mi"
  }
  set {
    name  = "dapr_scheduler.resources.limits.memory"
    value = "512Mi"
  }
}
