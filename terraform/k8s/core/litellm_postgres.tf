locals {
  litellm_db_cluster = "litellm-postgres"
  litellm_db_secret  = "litellm-postgres-app"
  litellm_db_name    = "litellm"
  litellm_db_user    = "litellm"
}

resource "random_password" "litellm_postgres" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "litellm_db_password" {
  name  = "/powerlifting/litellm/db_password"
  type  = "SecureString"
  value = random_password.litellm_postgres.result
}

resource "kubernetes_secret_v1" "litellm_postgres" {
  metadata {
    name      = local.litellm_db_secret
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }
  data = {
    username = local.litellm_db_user
    password = random_password.litellm_postgres.result
  }
  type = "kubernetes.io/basic-auth"
}

resource "kubectl_manifest" "litellm_postgres" {
  yaml_body = yamlencode({
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "Cluster"
    metadata = {
      name      = local.litellm_db_cluster
      namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    }
    spec = {
      instances             = 1
      primaryUpdateStrategy = "unsupervised"
      storage = {
        storageClass = kubernetes_storage_class_v1.postgres.metadata[0].name
        size         = "1Gi"
      }
      bootstrap = {
        initdb = {
          database = local.litellm_db_name
          owner    = local.litellm_db_user
          secret = {
            name = local.litellm_db_secret
          }
        }
      }
    }
  })

  depends_on = [helm_release.cnpg, kubernetes_secret_v1.litellm_postgres]
}
