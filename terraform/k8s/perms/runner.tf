resource "kubernetes_service_account_v1" "runner" {
  metadata {
    name      = "powerlifting-deployer"
    namespace = var.runner_namespace
  }
}

resource "kubernetes_cluster_role_binding_v1" "runner_cluster" {
  metadata {
    name = "powerlifting-deployer"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.runner.metadata[0].name
    namespace = var.runner_namespace
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "cluster-admin"
  }
}
