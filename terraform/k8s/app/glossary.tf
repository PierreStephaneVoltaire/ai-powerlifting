resource "kubernetes_deployment_v1" "glossary" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-glossary"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 1

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = { app = "pl-glossary" }
    }

    template {
      metadata {
        labels = { app = "pl-glossary", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name             = "pl-glossary"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "glossary"
          image             = local.images.glossary
          image_pull_policy = "IfNotPresent"

          env {
            name  = "PORT"
            value = "8000"
          }

          env {
            name  = "PL_PROFILE_URL"
            value = "http://pl-profile.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "VALKEY_URL"
            value = local.service_env.VALKEY_URL
          }

          env {
            name  = "PROMPT_CACHE_URL"
            value = local.service_env.PROMPT_CACHE_URL
          }

          env {
            name  = "IF_API_URL"
            value = local.service_env.IF_API_URL
          }

          env {
            name  = "GLOSSARY_GENERIC_INTERVAL"
            value = "5m"
          }

          env {
            name  = "GOMEMLIMIT"
            value = "100MiB"
          }

          dynamic "env" {
            for_each = module.workload_aws["pl-glossary"].env
            content {
              name  = env.key
              value = env.value
            }
          }

          env {
            name  = "PL_JOB_TOKEN_PUBLIC_KEY"
            value = local.job_token_public_key
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }

          port {
            container_port = 8000
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "500m", memory = "128Mi" }
            requests = { cpu = "25m", memory = "32Mi" }
          }

          readiness_probe {
            http_get {
              path = "/healthz"
              port = 8000
            }
            initial_delay_seconds = 3
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/healthz"
              port = 8000
            }
            initial_delay_seconds = 10
            period_seconds        = 20
          }

          volume_mount {
            name       = "aws"
            mount_path = module.workload_aws["pl-glossary"].mount_path
            read_only  = true
          }
        }

        volume {
          name = "aws"

          dynamic "secret" {
            for_each = module.workload_aws["pl-glossary"].secret_names
            content {
              secret_name = secret.value
            }
          }

          dynamic "projected" {
            for_each = module.workload_aws["pl-glossary"].token_paths
            content {
              sources {
                service_account_token {
                  audience           = "sts.amazonaws.com"
                  expiration_seconds = 3600
                  path               = projected.value
                }
              }
            }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "glossary" {
  metadata {
    name      = "pl-glossary"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-glossary" }

    port {
      port        = 8000
      target_port = 8000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
