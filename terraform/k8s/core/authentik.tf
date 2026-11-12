locals {
  authentik_version          = "2026.5.3"
  authentik_bootstrap_script = <<-EOT
    import os, sys, django
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "authentik.root.settings")
    django.setup()
    from authentik.core.models import User, Token

    user, created = User.objects.get_or_create(
        username="akadmin",
        defaults={
            "email": os.environ.get("AUTHENTIK_BOOTSTRAP_EMAIL", "root@example.com"),
            "name": "authentik Default Admin",
            "is_superuser": True,
        },
    )
    if created:
        user.set_password(os.environ.get("AUTHENTIK_BOOTSTRAP_PASSWORD", "authentik"))
        user.save()

    token, tok_created = Token.objects.get_or_create(
        identifier="terraform-provider",
        user=user,
        defaults={"intent": "api", "expiring": False},
    )
    if tok_created:
        token.key = os.environ["AUTHENTIK_BOOTSTRAP_TOKEN"]
        token.save()

    print("TOKEN:" + token.key)
  EOT
}

resource "random_password" "authentik_secret_key" {
  length  = 60
  special = false
}

resource "kubernetes_secret_v1" "authentik_env" {
  metadata {
    name      = "authentik-env"
    namespace = kubernetes_namespace_v1.auth.metadata[0].name
    labels = {
      app = "authentik"
    }
  }
  data = {
    AUTHENTIK_SECRET_KEY           = random_password.authentik_secret_key.result
    AUTHENTIK_POSTGRESQL__HOST     = local.postgres_host
    AUTHENTIK_POSTGRESQL__PORT     = "5432"
    AUTHENTIK_POSTGRESQL__NAME     = local.postgres_database
    AUTHENTIK_POSTGRESQL__USER     = local.postgres_username
    AUTHENTIK_POSTGRESQL__PASSWORD = random_password.postgres.result
    AUTHENTIK_BOOTSTRAP_EMAIL      = var.authentik_bootstrap_email
    AUTHENTIK_BOOTSTRAP_PASSWORD   = var.authentik_bootstrap_password
    AUTHENTIK_BOOTSTRAP_TOKEN      = var.authentik_bootstrap_token
  }
  type = "Opaque"
}

resource "kubernetes_secret_v1" "authentik_token" {
  metadata {
    name      = "authentik-terraform-token"
    namespace = kubernetes_namespace_v1.auth.metadata[0].name
    labels = {
      app = "authentik"
    }
  }
  data = {
    token = var.authentik_bootstrap_token
  }
  type = "Opaque"
}

resource "helm_release" "authentik" {
  name       = "authentik"
  repository = "https://charts.goauthentik.io"
  chart      = "authentik"
  version    = local.authentik_version
  namespace  = kubernetes_namespace_v1.auth.metadata[0].name

  set {
    name  = "authentik.existingSecret.secretName"
    value = kubernetes_secret_v1.authentik_env.metadata[0].name
  }
  set {
    name  = "postgresql.enabled"
    value = "false"
  }
  set {
    name  = "redis.enabled"
    value = "true"
  }
  set {
    name  = "server.replicas"
    value = "1"
  }
  set {
    name  = "worker.replicas"
    value = "1"
  }
}

resource "kubernetes_job_v1" "authentik_bootstrap_token" {
  metadata {
    name      = "authentik-bootstrap-token"
    namespace = kubernetes_namespace_v1.auth.metadata[0].name
    labels = {
      app = "authentik"
    }
  }

  spec {
    backoff_limit = 4
    template {
      metadata {
        labels = {
          app = "authentik"
        }
      }
      spec {
        restart_policy = "Never"
        container {
          name    = "bootstrap"
          image   = "ghcr.io/goauthentik/server:${local.authentik_version}"
          command = ["python", "/manage.py", "shell", "-c", local.authentik_bootstrap_script]
          env_from {
            secret_ref {
              name = kubernetes_secret_v1.authentik_env.metadata[0].name
            }
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_secret_v1.authentik_token,
    helm_release.authentik,
  ]
}

resource "kubernetes_secret_v1" "authentik_powerlifting_env" {
  metadata {
    name      = "authentik-env"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    labels = {
      app = "authentik"
    }
  }
  data = {
    AUTHENTIK_SECRET_KEY           = random_password.authentik_secret_key.result
    AUTHENTIK_POSTGRESQL__HOST     = local.authentik_db_host
    AUTHENTIK_POSTGRESQL__PORT     = "5432"
    AUTHENTIK_POSTGRESQL__NAME     = local.postgres_database
    AUTHENTIK_POSTGRESQL__USER     = local.postgres_username
    AUTHENTIK_POSTGRESQL__PASSWORD = random_password.postgres.result
    AUTHENTIK_BOOTSTRAP_EMAIL      = var.authentik_bootstrap_email
    AUTHENTIK_BOOTSTRAP_PASSWORD   = var.authentik_bootstrap_password
    AUTHENTIK_BOOTSTRAP_TOKEN      = var.authentik_bootstrap_token
  }
  type = "Opaque"
}

resource "kubernetes_secret_v1" "authentik_powerlifting_token" {
  metadata {
    name      = "authentik-terraform-token"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    labels = {
      app = "authentik"
    }
  }
  data = {
    token = var.authentik_bootstrap_token
  }
  type = "Opaque"
}

resource "helm_release" "authentik_powerlifting" {
  name       = "authentik"
  repository = "https://charts.goauthentik.io"
  chart      = "authentik"
  version    = local.authentik_version
  namespace  = kubernetes_namespace_v1.powerlifting.metadata[0].name
  timeout    = 900

  set {
    name  = "authentik.existingSecret.secretName"
    value = kubernetes_secret_v1.authentik_powerlifting_env.metadata[0].name
  }
  set {
    name  = "postgresql.enabled"
    value = "false"
  }
  set {
    name  = "redis.enabled"
    value = "true"
  }
  set {
    name  = "server.replicas"
    value = "1"
  }
  set {
    name  = "worker.replicas"
    value = "1"
  }

  depends_on = [kubectl_manifest.authentik_postgres]
}

resource "kubernetes_job_v1" "authentik_powerlifting_bootstrap_token" {
  metadata {
    name      = "authentik-bootstrap-token"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
    labels = {
      app = "authentik"
    }
  }

  spec {
    backoff_limit = 4
    template {
      metadata {
        labels = {
          app = "authentik"
        }
      }
      spec {
        restart_policy = "Never"
        container {
          name    = "bootstrap"
          image   = "ghcr.io/goauthentik/server:${local.authentik_version}"
          command = ["python", "/manage.py", "shell", "-c", local.authentik_bootstrap_script]
          env_from {
            secret_ref {
              name = kubernetes_secret_v1.authentik_powerlifting_env.metadata[0].name
            }
          }
        }
      }
    }
  }

  depends_on = [
    kubernetes_secret_v1.authentik_powerlifting_token,
    helm_release.authentik_powerlifting,
  ]
}
