data "aws_ecr_authorization_token" "registry" {}

resource "kubernetes_cron_job_v1" "registry_refresher" {
  metadata {
    name      = "ecr-token-refresher"
    namespace = var.namespace
  }

  spec {
    schedule                      = "0 */6 * * *"
    concurrency_policy            = "Forbid"
    failed_jobs_history_limit     = 3
    successful_jobs_history_limit = 1
    starting_deadline_seconds     = 120

    job_template {
      metadata {}

      spec {
        backoff_limit = 2

        template {
          metadata {}

          spec {
            service_account_name = "ecr-refresher"
            restart_policy       = "OnFailure"

            container {
              name    = "refresher"
              image   = "alpine/k8s:1.34.5"
              command = ["/bin/sh", "-c"]
              args = [<<-EOT
                set -eu
                TOKEN=$(aws ecr get-login-password --region ${var.region})
                kubectl create secret docker-registry ecr-registry \
                  --namespace ${var.namespace} \
                  --docker-server=${replace(data.aws_ecr_authorization_token.registry.proxy_endpoint, "https://", "")} \
                  --docker-username=AWS \
                  --docker-password="$TOKEN" \
                  --dry-run=client -o json \
                  | kubectl patch secret ecr-registry --namespace ${var.namespace} --type merge --patch-file /dev/stdin
              EOT
              ]

              env {
                name  = "AWS_SHARED_CREDENTIALS_FILE"
                value = "/secrets/aws/credentials"
              }

              env {
                name  = "AWS_CONFIG_FILE"
                value = "/secrets/aws/config"
              }

              resources {
                requests = { cpu = "50m", memory = "64Mi" }
                limits   = { cpu = "100m", memory = "128Mi" }
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
  }
}
