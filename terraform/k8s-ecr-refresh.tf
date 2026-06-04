
resource "kubernetes_service_account" "ecr_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app        = "ecr-refresher"
      managed-by = "terraform"
    }
  }
}

# Needs patch on secrets in if-portals only
resource "kubernetes_role" "ecr_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["secrets"]
    verbs      = ["get", "patch"]
  }
}

resource "kubernetes_role_binding" "ecr_refresher" {
  metadata {
    name      = "ecr-refresher"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.ecr_refresher.metadata[0].name
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  role_ref {
    kind      = "Role"
    name      = kubernetes_role.ecr_refresher.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

# Also needs patch on ecr-secret in the default namespace
resource "kubernetes_role" "ecr_refresher_default" {
  metadata {
    name      = "ecr-refresher"
    namespace = "default"
  }

  rule {
    api_groups = [""]
    resources  = ["secrets"]
    verbs      = ["get", "patch"]
  }
}

resource "kubernetes_role_binding" "ecr_refresher_default" {
  metadata {
    name      = "ecr-refresher"
    namespace = "default"
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.ecr_refresher.metadata[0].name
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  role_ref {
    kind      = "Role"
    name      = kubernetes_role.ecr_refresher_default.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_cron_job_v1" "ecr_refresher" {
  metadata {
    name      = "ecr-token-refresher"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
    labels = {
      app        = "ecr-refresher"
      managed-by = "terraform"
    }
  }

  spec {
    # Every 6 hours — well within the 12-hour ECR token expiry window
    schedule                      = "0 */6 * * *"
    concurrency_policy            = "Forbid"
    failed_jobs_history_limit     = 3
    successful_jobs_history_limit = 3
    starting_deadline_seconds     = 120

    job_template {
      metadata {
        labels = {
          app = "ecr-refresher"
        }
      }

      spec {
        backoff_limit = 2

        template {
          metadata {
            labels = {
              app = "ecr-refresher"
            }
          }

          spec {
            service_account_name = kubernetes_service_account.ecr_refresher.metadata[0].name
            restart_policy       = "OnFailure"

            # Mount the same host-path AWS credentials used by all other pods
            volume {
              name = "aws-credentials"
              host_path {
                path = var.aws_credentials_host_path
                type = "Directory"
              }
            }

            container {
              name  = "refresher"
              image = "amazon/aws-cli:latest"

              command = ["/bin/sh", "-c"]
              args = [<<-EOT
                set -e
                echo "Fetching fresh ECR token..."
                TOKEN=$(aws ecr get-login-password --region ${var.region})
                REGISTRY="${data.aws_ecr_authorization_token.private.proxy_endpoint}"
                REGISTRY="${replace(data.aws_ecr_authorization_token.private.proxy_endpoint, "https://", "")}"
                AUTH=$(echo -n "AWS:$TOKEN" | base64 -w 0)
                DOCKERCONFIG=$(printf '{"auths":{"%s":{"username":"AWS","password":"%s","auth":"%s"}}}' "$REGISTRY" "$TOKEN" "$AUTH")
                ENCODED=$(echo -n "$DOCKERCONFIG" | base64 -w 0)

                echo "Patching ecr-registry in ${kubernetes_namespace.if_portals.metadata[0].name}..."
                kubectl patch secret ecr-registry \
                  -n ${kubernetes_namespace.if_portals.metadata[0].name} \
                  --type='json' \
                  -p="[{\"op\":\"replace\",\"path\":\"/data/.dockerconfigjson\",\"value\":\"$ENCODED\"}]"

                echo "Patching ecr-secret in default..."
                kubectl patch secret ecr-secret \
                  -n default \
                  --type='json' \
                  -p="[{\"op\":\"replace\",\"path\":\"/data/.dockerconfigjson\",\"value\":\"$ENCODED\"}]"

                echo "Done. ECR secrets refreshed successfully."
              EOT
              ]

              env {
                name  = "AWS_DEFAULT_REGION"
                value = var.region
              }

              volume_mount {
                name       = "aws-credentials"
                mount_path = "/root/.aws"
                read_only  = true
              }

              resources {
                requests = {
                  cpu    = "50m"
                  memory = "64Mi"
                }
                limits = {
                  cpu    = "100m"
                  memory = "128Mi"
                }
              }
            }
          }
        }
      }
    }
  }
}
