resource "kubernetes_deployment" "if_agent_api" {
  metadata {
    name      = "if-agent-api"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app = "if-agent-api"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "if-agent-api"
      }
    }

    template {
      metadata {
        labels = {
          app = "if-agent-api"
        }
        annotations = {
          "checksum/config"       = sha1(jsonencode(kubernetes_config_map.if_agent_api_config.data))
          "checksum/model-config" = sha1(jsonencode(kubernetes_config_map.if_agent_api_model_config.data))
        }
      }

      spec {
        service_account_name = kubernetes_service_account.if_agent_api.metadata[0].name

        image_pull_secrets {
          name = kubernetes_secret.ecr_registry.metadata[0].name
        }

        volume {
          name = "data-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.if_agent_data.metadata[0].name
          }
        }

        volume {
          name = "sandbox-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.if_agent_sandbox.metadata[0].name
          }
        }

        volume {
          name = "conversations-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.if_agent_conversations.metadata[0].name
          }
        }

        volume {
          name = "facts-storage"
          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim.if_agent_facts.metadata[0].name
          }
        }

        volume {
          name = "aws-credentials"
          host_path {
            path = var.aws_credentials_host_path
            type = "Directory"
          }
        }

        volume {
          name = "tools-directory"
          host_path {
            path = var.tools_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "specialists-directory"
          host_path {
            path = var.specialists_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "models-directory"
          host_path {
            path = var.models_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "scripts-directory"
          host_path {
            path = var.scripts_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "skills-directory"
          host_path {
            path = var.skills_host_path
            type = "DirectoryOrCreate"
          }
        }

        container {
          name              = "api"
          image             = "${aws_ecr_repository.if_agent_api.repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 8000
          }

          resources {
            limits = {
              memory = "${var.api_memory_mb}Mi"
              cpu    = "${var.api_cpu_millicores}m"
            }
            requests = {
              memory = "${var.api_memory_request_mb}Mi"
              cpu    = "${var.api_cpu_request_millicores}m"
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.if_agent_api_config.metadata[0].name
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.if_agent_api_model_config.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.if_agent_api_secrets.metadata[0].name
            }
          }

          volume_mount {
            name       = "data-storage"
            mount_path = "/app/src/data"
          }

          volume_mount {
            name       = "sandbox-storage"
            mount_path = "/app/src/sandbox"
          }

          volume_mount {
            name       = "conversations-storage"
            mount_path = "/app/src/data/conversations"
          }

          volume_mount {
            name       = "facts-storage"
            mount_path = "/app/src/data/facts"
          }

          volume_mount {
            name       = "aws-credentials"
            mount_path = "/root/.aws"
            read_only  = true
          }

          volume_mount {
            name       = "tools-directory"
            mount_path = "/app/tools"
            read_only  = true
          }

          volume_mount {
            name       = "specialists-directory"
            mount_path = "/app/specialists"
            read_only  = true
          }

          volume_mount {
            name       = "models-directory"
            mount_path = "/app/models"
            read_only  = true
          }

          volume_mount {
            name       = "scripts-directory"
            mount_path = "/app/scripts"
            read_only  = true
          }

          volume_mount {
            name       = "skills-directory"
            mount_path = "/app/skills"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 120
            timeout_seconds       = 30
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 60
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build_main_api]
}

locals {
  portals = {
    main-portal = {
      port        = 3000
      has_db      = false
      db_table    = null
      has_secrets = false
    }
    finance-portal = {
      port        = 3002
      has_db      = true
      db_table    = "if-finance"
      has_secrets = false
    }
    diary-portal = {
      port        = 3003
      has_db      = true
      db_table    = "if-diary"
      has_secrets = false
    }
    proposals-portal = {
      port        = 3004
      has_db      = true
      db_table    = "if-proposals"
      has_secrets = false
    }
    powerlifting-app = {
      port        = 3005
      has_db      = true
      db_table    = "powerlifting"
      has_secrets = false
    }
    directives-portal = {
      port        = 3006
      has_db      = true
      db_table    = "if-core"
      has_secrets = true
    }
  }

  portal_backend_config_checksums = {
    "main-portal"       = sha1(jsonencode(kubernetes_config_map.main_portal_config.data))
    "finance-portal"    = sha1(jsonencode(kubernetes_config_map.finance_portal_config.data))
    "diary-portal"      = sha1(jsonencode(kubernetes_config_map.diary_portal_config.data))
    "proposals-portal"  = sha1(jsonencode(kubernetes_config_map.proposals_portal_config.data))
    "powerlifting-app"  = nonsensitive(sha1(jsonencode(kubernetes_config_map.powerlifting_app_config.data)))
    "directives-portal" = nonsensitive(sha1(join("", [jsonencode(kubernetes_config_map.directives_portal_config.data), jsonencode(kubernetes_secret.directives_portal_secrets.data)])))
  }
}

resource "kubernetes_deployment" "portal_backends" {
  for_each = local.portals

  metadata {
    name      = "${each.key}-backend"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app = "${each.key}-backend"
    }
  }

  spec {
    replicas = contains(keys(local.public_apps), each.key) ? 1 : 0

    selector {
      match_labels = {
        app = "${each.key}-backend"
      }
    }

    template {
      metadata {
        labels = {
          app = "${each.key}-backend"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = tostring(each.value.port)
          "prometheus.io/path"   = "/metrics"
          "checksum/config"      = local.portal_backend_config_checksums[each.key]
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.ecr_registry.metadata[0].name
        }

        volume {
          name = "aws-credentials"
          host_path {
            path = var.aws_credentials_host_path
            type = "Directory"
          }
        }

        container {
          name              = "backend"
          image             = "${aws_ecr_repository.portal_backends["${each.key}-backend"].repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = each.value.port
          }

          resources {
            limits = {
              memory = "${var.portal_memory_mb}Mi"
              cpu    = "${var.portal_cpu_millicores}m"
            }
            requests = {
              memory = "${var.portal_memory_mb / 2}Mi"
              cpu    = "${var.portal_cpu_millicores / 2}m"
            }
          }

          env_from {
            config_map_ref {
              name = "${each.key}-config"
            }
          }

          dynamic "env_from" {
            for_each = each.value.has_secrets ? [1] : []
            content {
              secret_ref {
                name = "${each.key}-secrets"
              }
            }
          }

          volume_mount {
            name       = "aws-credentials"
            mount_path = "/root/.aws"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = each.value.port
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = each.value.port
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build_portal_backends]
}

resource "kubernetes_deployment" "portal_frontends" {
  for_each = local.portals

  metadata {
    name      = "${each.key}-frontend"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app = "${each.key}-frontend"
    }
  }

  spec {
    replicas = contains(keys(local.public_apps), each.key) ? 1 : 0

    selector {
      match_labels = {
        app = "${each.key}-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app = "${each.key}-frontend"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.ecr_registry.metadata[0].name
        }

        container {
          name              = "frontend"
          image             = "${aws_ecr_repository.portal_frontends["${each.key}-frontend"].repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 3001
          }

          resources {
            limits = {
              memory = "${var.frontend_memory_mb}Mi"
              cpu    = "${var.frontend_cpu_millicores}m"
            }
            requests = {
              memory = "${var.frontend_memory_mb / 2}Mi"
              cpu    = "${var.frontend_cpu_millicores / 2}m"
            }
          }

          env_from {
            config_map_ref {
              name = "${each.key}-config"
            }
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 3001
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 3001
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }

  depends_on = [
    null_resource.packer_build_portal_frontends,
    kubernetes_deployment.portal_backends,
  ]
}
