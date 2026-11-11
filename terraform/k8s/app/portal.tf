resource "kubernetes_deployment_v1" "backend" {
  wait_for_rollout = false

  metadata {
    name      = "powerlifting-app-backend"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "powerlifting-app-backend" }
    }

    template {
      metadata {
        labels = { app = "powerlifting-app-backend", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "powerlifting-app-backend"
        automount_service_account_token = false
        enable_service_links            = false

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "backend"
          image             = local.images.backend
          image_pull_policy = "IfNotPresent"

          port {
            container_port = 3005
            name           = "http"
            protocol       = "TCP"
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }

          env {
            name  = "PL_SECURITY_URL"
            value = "http://pl-security.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name = "PL_PRINCIPAL_PUBLIC_KEY"
            value_from {
              secret_key_ref {
                name = "pl-security-signing-key"
                key  = "public_key"
              }
            }
          }

          env {
            name = "MEDIA_SIGNING_PRIVATE_KEY"
            value_from {
              secret_key_ref {
                name = "powerlifting-app-secrets"
                key  = "MEDIA_SIGNING_PRIVATE_KEY"
              }
            }
          }

          resources {
            limits   = { cpu = "500m", memory = "1Gi" }
            requests = { cpu = "250m", memory = "512Mi" }
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 3005
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 3005
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }

          volume_mount {
            name       = "aws"
            mount_path = "/secrets/aws"
            read_only  = true
          }
        }

        volume {
          name = "aws"

          secret {
            secret_name = "pl-aws-credentials"
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "backend" {
  metadata {
    name      = "powerlifting-app-backend"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "powerlifting-app-backend" }

    port {
      port        = 3005
      target_port = 3005
      name        = "http"
      protocol    = "TCP"
    }
  }
}

resource "kubernetes_deployment_v1" "frontend" {
  wait_for_rollout = false

  metadata {
    name      = "powerlifting-app-frontend"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "powerlifting-app-frontend" }
    }

    template {
      metadata {
        labels = { app = "powerlifting-app-frontend", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "powerlifting-app-frontend"
        automount_service_account_token = false
        enable_service_links            = false

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "frontend"
          image             = local.images.frontend
          image_pull_policy = "IfNotPresent"

          port {
            container_port = 3001
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "250m", memory = "512Mi" }
            requests = { cpu = "125m", memory = "256Mi" }
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
}

resource "kubernetes_service_v1" "frontend" {
  metadata {
    name      = "powerlifting-app-frontend"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "powerlifting-app-frontend" }

    port {
      port        = 3001
      target_port = 3001
      name        = "http"
      protocol    = "TCP"
    }
  }
}
