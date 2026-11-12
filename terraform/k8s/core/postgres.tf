locals {
  postgres_database    = "authentik"
  postgres_username    = "authentik"
  authentik_db_cluster = "authentik-postgres"
  authentik_db_secret  = "authentik-postgres-app"
  authentik_db_host    = "${local.authentik_db_cluster}-rw.${var.namespace}.svc.cluster.local"
}

resource "kubernetes_storage_class_v1" "postgres" {
  metadata {
    name = "postgres-local-path"
  }

  storage_provisioner    = "rancher.io/local-path"
  reclaim_policy         = "Delete"
  volume_binding_mode    = "WaitForFirstConsumer"
  allow_volume_expansion = false
}

resource "random_password" "postgres" {
  length  = 32
  special = false
}
resource "helm_release" "cnpg" {
  name             = "cnpg"
  repository       = "https://cloudnative-pg.github.io/charts"
  chart            = "cloudnative-pg"
  version          = "0.29.0"
  namespace        = "cnpg-system"
  create_namespace = true

  set {
    name  = "config.clusterWide"
    value = "true"
  }
}
resource "kubernetes_secret_v1" "authentik_postgres" {
  metadata {
    name      = local.authentik_db_secret
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }
  data = {
    username = local.postgres_username
    password = random_password.postgres.result
  }
  type = "kubernetes.io/basic-auth"
}

resource "kubectl_manifest" "authentik_postgres" {
  yaml_body = yamlencode({
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "Cluster"
    metadata = {
      name      = local.authentik_db_cluster
      namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    }
    spec = {
      instances             = 2
      primaryUpdateStrategy = "unsupervised"
      storage = {
        storageClass = kubernetes_storage_class_v1.postgres.metadata[0].name
        size         = "10Gi"
      }
      bootstrap = {
        initdb = {
          database = local.postgres_database
          owner    = local.postgres_username
          secret = {
            name = local.authentik_db_secret
          }
        }
      }
    }
  })

  depends_on = [helm_release.cnpg, kubernetes_secret_v1.authentik_postgres]
}
