data "aws_ssm_parameter" "security_private_key" {
  name            = "/powerlifting/security/principal-signing-private-key"
  with_decryption = true
}

data "aws_ssm_parameter" "security_public_key" {
  name            = "/powerlifting/security/principal-signing-public-key"
  with_decryption = true
}

resource "random_password" "oauth2_proxy_cookie" {
  length  = 32
  special = false
}

data "kubernetes_secret_v1" "authentik_oidc" {
  metadata {
    name      = "authentik-powerlifting-oidc"
    namespace = var.auth_namespace
  }
}

resource "kubernetes_secret_v1" "oauth2_proxy" {
  metadata {
    name      = "oauth2-proxy-secrets"
    namespace = var.namespace
  }

  data = { OAUTH2_PROXY_CLIENT_SECRET = data.kubernetes_secret_v1.authentik_oidc.data["AUTHENTIK_CLIENT_SECRET"] }
}

resource "kubernetes_secret_v1" "security" {
  metadata {
    name      = "pl-security-signing-key"
    namespace = var.namespace
  }

  data = {
    private_key = data.aws_ssm_parameter.security_private_key.value
    public_key  = data.aws_ssm_parameter.security_public_key.value
  }
}

resource "kubernetes_deployment_v1" "security" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.central_authz, kubectl_manifest.authorized_destination, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "pl-security"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "pl-security" }
    }

    template {
      metadata {
        labels = { app = "pl-security", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "pl-security"
        automount_service_account_token = false
        enable_service_links            = false

        image_pull_secrets {
          name = "ecr-registry"
        }

        container {
          name              = "security"
          image             = local.images.services
          image_pull_policy = "IfNotPresent"
          command           = ["python", "-m", "services.security"]

          env {
            name  = "PL_SECURITY_URL"
            value = "http://pl-security.${var.namespace}.svc.cluster.local:8000"
          }

          env {
            name  = "AWS_SHARED_CREDENTIALS_FILE"
            value = "/secrets/aws/credentials"
          }

          env {
            name  = "AWS_CONFIG_FILE"
            value = "/secrets/aws/config"
          }

          env {
            name = "AUTHENTIK_ISSUER_URL"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_ISSUER_URL"
              }
            }
          }

          env {
            name = "AUTHENTIK_JWKS_URL"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_JWKS_URL"
              }
            }
          }

          env {
            name = "AUTHENTIK_CLIENT_ID"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_CLIENT_ID"
              }
            }
          }

          env {
            name  = "PL_SECURITY_WORKLOADS"
            value = jsonencode(local.security_workloads)
          }

          env {
            name  = "PL_SECURITY_ALLOWED_CALLERS"
            value = jsonencode(local.security_allowed_callers)
          }
          env {
            name  = "PL_SECURITY_AUTHORITIES"
            value = jsonencode(local.security_authorities)
          }
          env {
            name  = "PL_SECURITY_DELEGATION"
            value = jsonencode(local.security_delegation)
          }

          env {
            name = "PL_SECURITY_PRIVATE_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.security.metadata[0].name
                key  = "private_key"
              }
            }
          }

          env {
            name = "PL_PRINCIPAL_PUBLIC_KEY"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.security.metadata[0].name
                key  = "public_key"
              }
            }
          }

          env_from {
            config_map_ref {
              name = "powerlifting-app-config"
            }
          }

          port {
            name           = "http"
            container_port = 8000
            protocol       = "TCP"
          }

          port {
            name           = "grpc"
            container_port = 9000
            protocol       = "TCP"
          }
          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
          }

          resources {
            limits   = { cpu = "500m", memory = "512Mi" }
            requests = { cpu = "50m", memory = "128Mi" }
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

resource "kubernetes_service_v1" "security" {
  metadata {
    name      = "pl-security"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "pl-security" }

    port {
      name        = "http"
      port        = 8000
      target_port = 8000
      protocol    = "TCP"
    }

    port {
      name        = "grpc"
      port        = 9000
      target_port = 9000
      protocol    = "TCP"
    }
  }
}

resource "kubernetes_deployment_v1" "oauth2_proxy" {
  depends_on       = [kubectl_manifest.edge_only, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "oauth2-proxy"
    namespace = var.namespace
  }

  spec {
    replicas = 1

    selector {
      match_labels = { app = "oauth2-proxy" }
    }

    template {
      metadata {
        labels = { app = "oauth2-proxy", "istio.io/dataplane-mode" = "ambient" }
      }

      spec {
        service_account_name            = "oauth2-proxy"
        automount_service_account_token = false

        container {
          name              = "oauth2-proxy"
          image             = "quay.io/oauth2-proxy/oauth2-proxy:v7.15.6"
          image_pull_policy = "IfNotPresent"
          args = [
            "--http-address=0.0.0.0:4180",
            "--reverse-proxy=true",
            "--provider=oidc",
            "--redirect-url=https://${var.app_domain}/oauth2/callback",
            "--upstream=http://powerlifting-app-backend.${var.namespace}.svc.cluster.local:3005/",
            "--scope=openid profile email groups roles powerlifting_identity offline_access",
            "--code-challenge-method=S256",
            "--insecure-oidc-skip-nonce=false",
            "--cookie-refresh=1m",
            "--cookie-name=__Host-pl_oauth2_proxy",
            "--cookie-secure=true",
            "--cookie-httponly=true",
            "--cookie-samesite=lax",
            "--session-store-type=redis",
            "--redis-connection-url=redis://pl-valkey.${var.namespace}.svc.cluster.local:6379",
            "--pass-authorization-header=true",
            "--api-route=^/api/.*$",
            "--skip-auth-route=POST=^/api/auth/logout$",
            "--upstream-timeout=300s",
            "--skip-provider-button=true",
            "--silence-ping-logging=true",
          ]

          env {
            name = "OAUTH2_PROXY_OIDC_ISSUER_URL"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_ISSUER_URL"
              }
            }
          }

          env {
            name = "OAUTH2_PROXY_CLIENT_ID"
            value_from {
              config_map_key_ref {
                name = "powerlifting-app-config"
                key  = "AUTHENTIK_CLIENT_ID"
              }
            }
          }

          env {
            name = "OAUTH2_PROXY_CLIENT_SECRET"
            value_from {
              secret_key_ref {
                name = kubernetes_secret_v1.oauth2_proxy.metadata[0].name
                key  = "OAUTH2_PROXY_CLIENT_SECRET"
              }
            }
          }

          env {
            name  = "OAUTH2_PROXY_COOKIE_SECRET"
            value = random_password.oauth2_proxy_cookie.result
          }

          port {
            name           = "http"
            container_port = 4180
            protocol       = "TCP"
          }

          readiness_probe {
            http_get {
              path = "/ping"
              port = 4180
            }
          }

          resources {
            limits   = { cpu = "250m", memory = "256Mi" }
            requests = { cpu = "25m", memory = "64Mi" }
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "oauth2_proxy" {
  metadata {
    name      = "oauth2-proxy"
    namespace = var.namespace
  }

  spec {
    selector = { app = "oauth2-proxy" }

    port {
      name        = "http"
      port        = 4180
      target_port = 4180
      protocol    = "TCP"
    }
  }
}

locals {
  security_operations = flatten([for filename in fileset("${path.module}/../../../src/services/operations", "*.json") : jsondecode(file("${path.module}/../../../src/services/operations/${filename}"))])
  ai_operations       = [for operation in local.security_operations : operation.name if try(operation.execution, "") == "ai"]
  ai_domains          = toset([for operation in local.security_operations : operation.domain if try(operation.execution, "") == "ai"])

  security_workloads = merge(
    { "cluster.local/ns/${var.namespace}/sa/powerlifting-app-backend" = "pl-backend" },
    { for name in ["budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "cluster.local/ns/${var.namespace}/sa/pl-${name}" => "pl-${name}" },
    { "cluster.local/ns/${var.namespace}/sa/pl-coach" = "pl-coach" },
    { "cluster.local/ns/${var.namespace}/sa/pl-coach-discord" = "pl-coach-discord" },
    { "cluster.local/ns/${var.namespace}/sa/pl-security" = "pl-security" },
    { "cluster.local/ns/${var.namespace}/sa/pl-analytics" = "pl-analytics" },
    { "cluster.local/ns/${var.namespace}/sa/oauth2-proxy" = "pl-oauth2-proxy" },
  )

  security_allowed_callers = merge(
    { "cluster.local/ns/${var.namespace}/sa/powerlifting-app-backend" = concat(["pl-security", "pl-coach", "pl-coach-discord"], [for name in ["analytics", "budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "pl-${name}"]) },
    { for name in ["budget", "calculations", "competition", "export", "federation", "glossary", "goals", "imports", "lift-profiles", "performance", "profile", "program", "rankings", "sessions", "templates", "videos", "weight-log"] : "cluster.local/ns/${var.namespace}/sa/pl-${name}" => concat(["pl-security"], contains(local.ai_domains, name) ? ["pl-coach"] : []) },
    { "cluster.local/ns/${var.namespace}/sa/pl-analytics" = ["pl-security", "pl-budget", "pl-calculations", "pl-competition", "pl-federation", "pl-performance", "pl-profile", "pl-program", "pl-sessions", "pl-weight-log", "pl-coach"] },
    { "cluster.local/ns/${var.namespace}/sa/pl-coach" = ["pl-security", "pl-analytics", "pl-budget", "pl-calculations", "pl-competition", "pl-export", "pl-federation", "pl-glossary", "pl-goals", "pl-imports", "pl-lift-profiles", "pl-performance", "pl-profile", "pl-program", "pl-rankings", "pl-sessions", "pl-templates", "pl-videos", "pl-weight-log"] },
    { "cluster.local/ns/${var.namespace}/sa/pl-coach-discord" = ["pl-security", "pl-coach"] },
    { "cluster.local/ns/${var.namespace}/sa/pl-security" = [] },
  )

  security_delegation = merge(
    { "conversation_turn" = concat(["access_context"], [for operation in local.security_operations : operation.name]) },
    { "domain_job_read" = local.ai_operations, "domain_job_cancel" = local.ai_operations },
    { for operation in local.ai_operations : operation => ["domain_resume", "access_context", operation] },
    { "generation_status" = ["domain_job_read"] },
  )
}
