locals {
  assistant_db_cluster = "assistant-postgres"
  assistant_db_secret  = "assistant-postgres-app"
  assistant_db_name    = "assistant"
  assistant_db_user    = "assistant"
  assistant_db_host    = "${local.assistant_db_cluster}-rw.${kubernetes_namespace_v1.powerlifting.metadata[0].name}.svc"
}

resource "random_password" "assistant_postgres" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "assistant_db_password" {
  name  = "/powerlifting/assistant/db_password"
  type  = "SecureString"
  value = random_password.assistant_postgres.result
}

resource "kubernetes_secret_v1" "assistant_postgres" {
  metadata {
    name      = local.assistant_db_secret
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }
  data = {
    username = local.assistant_db_user
    password = random_password.assistant_postgres.result
  }
  type = "kubernetes.io/basic-auth"
}

resource "kubernetes_secret_v1" "assistant_postgres_connection" {
  metadata {
    name      = "assistant-postgres-connection"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }
  data = {
    host     = local.assistant_db_host
    port     = "5432"
    dbname   = local.assistant_db_name
    user     = local.assistant_db_user
    password = random_password.assistant_postgres.result
  }
}

resource "kubectl_manifest" "assistant_postgres" {
  yaml_body = yamlencode({
    apiVersion = "postgresql.cnpg.io/v1"
    kind       = "Cluster"
    metadata = {
      name      = local.assistant_db_cluster
      namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    }
    spec = {
      instances             = 1
      imageName             = "ghcr.io/cloudnative-pg/postgresql:18.4-standard-trixie"
      primaryUpdateStrategy = "unsupervised"
      storage = {
        storageClass = kubernetes_storage_class_v1.postgres.metadata[0].name
        size         = "2Gi"
      }
      bootstrap = {
        initdb = {
          database = local.assistant_db_name
          owner    = local.assistant_db_user
          secret = {
            name = local.assistant_db_secret
          }
          postInitApplicationSQL = [
            "CREATE EXTENSION IF NOT EXISTS vector"
          ]
        }
      }
    }
  })

  depends_on = [helm_release.cnpg, kubernetes_secret_v1.assistant_postgres]
}
