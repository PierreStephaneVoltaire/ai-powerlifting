locals {
  mcp_server_image_tag = "latest"

  mcp_default_pod_config = {
    replicas = 1
    resources = {
      requests = { cpu = "50m", memory = "64Mi" }
      limits   = { cpu = "500m", memory = "256Mi" }
    }
  }

  mcp_pod_configs = {
    for cat in local.mcp_server_categories : cat => (
      fileexists("${path.module}/../tools/${cat}/pod.yaml")
      ? yamldecode(file("${path.module}/../tools/${cat}/pod.yaml"))
      : local.mcp_default_pod_config
    )
  }

  mcp_k8s_names = {
    for cat in local.mcp_server_categories :
    cat => "if-mcp-${replace(cat, "_", "-")}"
  }
}

resource "kubernetes_service_account" "if_mcp_servers" {
  metadata {
    name      = "if-mcp-servers"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app        = "if-mcp-servers"
      managed-by = "terraform"
    }
  }

  automount_service_account_token = true
}

resource "kubernetes_deployment" "if_mcp_servers" {
  for_each = local.mcp_server_categories

  metadata {
    name      = local.mcp_k8s_names[each.key]
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app          = local.mcp_k8s_names[each.key]
      mcp_category = each.key
      managed-by   = "terraform"
    }
  }

  spec {
    replicas = lookup(local.mcp_pod_configs[each.key], "replicas", 1)

    selector {
      match_labels = {
        app          = local.mcp_k8s_names[each.key]
        mcp_category = each.key
      }
    }

    template {
      metadata {
        labels = {
          app          = local.mcp_k8s_names[each.key]
          mcp_category = each.key
        }
        annotations = {
          "checksum/pod-yaml" = fileexists("${path.module}/../tools/${each.key}/pod.yaml") ? filebase64sha256("${path.module}/../tools/${each.key}/pod.yaml") : "none"
        }
      }

      spec {
        service_account_name = kubernetes_service_account.if_mcp_servers.metadata[0].name

        image_pull_secrets {
          name = kubernetes_secret.ecr_registry.metadata[0].name
        }

        volume {
          name = "tools-code"
          host_path {
            path = "${var.tools_host_path}/${each.key}"
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "aws-credentials"
          host_path {
            path = var.aws_credentials_host_path
            type = "Directory"
          }
        }

        container {
          name              = "mcp"
          image             = "${aws_ecr_repository.if_mcp_base.repository_url}:${local.mcp_server_image_tag}"
          image_pull_policy = "Always"

          port {
            container_port = 8000
          }

          env {
            name  = "MCP_CATEGORY"
            value = each.key
          }
          env {
            name  = "MCP_PORT"
            value = "8000"
          }
          env {
            name  = "IF_TOOLS_ROOT"
            value = "/app/tools"
          }
          env {
            name  = "AWS_REGION"
            value = var.region
          }
          env {
            name  = "PYTHONUNBUFFERED"
            value = "1"
          }

          resources {
            limits   = local.mcp_pod_configs[each.key].resources.limits
            requests = local.mcp_pod_configs[each.key].resources.requests
          }

          liveness_probe {
            tcp_socket {
              port = 8000
            }
            initial_delay_seconds = 300
            period_seconds        = 30
            timeout_seconds       = 5
            failure_threshold     = 3
          }
          readiness_probe {
            tcp_socket {
              port = 8000
            }
            initial_delay_seconds = 300
            period_seconds        = 10
            timeout_seconds       = 3
            failure_threshold     = 3
          }

          volume_mount {
            name       = "tools-code"
            mount_path = "/app/tools/${each.key}"
            read_only  = true
          }
          volume_mount {
            name       = "aws-credentials"
            mount_path = "/root/.aws"
            read_only  = true
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build_mcp_base]
}

resource "kubernetes_service" "if_mcp_servers" {
  for_each = local.mcp_server_categories

  metadata {
    name      = local.mcp_k8s_names[each.key]
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app          = local.mcp_k8s_names[each.key]
      mcp_category = each.key
    }
  }

  spec {
    selector = {
      app          = local.mcp_k8s_names[each.key]
      mcp_category = each.key
    }

    port {
      name        = "mcp"
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }

    type = "ClusterIP"
  }
}
