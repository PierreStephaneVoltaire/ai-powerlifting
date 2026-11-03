resource "kubernetes_service_account_v1" "runner" {
  metadata {
    name      = "powerlifting-deployer"
    namespace = var.runner_namespace
  }
}

resource "kubernetes_role_binding_v1" "runner_namespace" {
  metadata {
    name      = "powerlifting-deployer"
    namespace = var.namespace
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account_v1.runner.metadata[0].name
    namespace = var.runner_namespace
  }

  role_ref {
    api_group = "rbac.authorization.k8s.io"
    kind      = "ClusterRole"
    name      = "admin"
  }
}

resource "kubernetes_cluster_role_v1" "runner_cluster" {
  metadata {
    name = "powerlifting-deployer"
  }

  rule {
    api_groups = [""]
    resources  = ["namespaces"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = ["apiextensions.k8s.io"]
    resources  = ["customresourcedefinitions"]
    verbs      = ["get", "list", "watch", "create", "update", "patch"]
  }

  rule {
    api_groups = ["rbac.authorization.k8s.io"]
    resources  = ["clusterroles", "clusterrolebindings", "roles", "rolebindings"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete", "bind", "escalate"]
  }

  rule {
    api_groups = ["gateway.networking.k8s.io"]
    resources  = ["gatewayclasses"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = ["admissionregistration.k8s.io"]
    resources  = ["validatingwebhookconfigurations", "mutatingwebhookconfigurations"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = [""]
    resources  = ["serviceaccounts", "secrets", "configmaps", "services", "pods"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = ["apps"]
    resources  = ["deployments"]
    verbs      = ["get", "list", "watch", "create", "update", "patch", "delete"]
  }

  rule {
    api_groups = ["actions.github.com"]
    resources  = ["*"]
    verbs      = ["*"]
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
    name      = kubernetes_cluster_role_v1.runner_cluster.metadata[0].name
  }
}
