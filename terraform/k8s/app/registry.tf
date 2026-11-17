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
              image   = "public.ecr.aws/aws-cli/aws-cli:2.37.0"
              command = ["/bin/sh", "-c"]
              args = [<<-EOT
                set -eu
                TOKEN=$(aws ecr get-login-password --region ${var.region})
                AUTH=$(printf 'AWS:%s' "$TOKEN" | base64 -w0)
                CONFIG=$(jq -nc --arg server "${replace(data.aws_ecr_authorization_token.registry.proxy_endpoint, "https://", "")}" --arg token "$TOKEN" --arg auth "$AUTH" '{auths: {($server): {username: "AWS", password: $token, auth: $auth}}}')
                PATCH=$(jq -nc --arg config "$(printf '%s' "$CONFIG" | base64 -w0)" '{data: {".dockerconfigjson": $config}}')
                SA=/var/run/secrets/kubernetes.io/serviceaccount
                status=$(curl -s -o /tmp/response -w '%%{http_code}' -X PATCH --cacert "$SA/ca.crt" -H "Authorization: Bearer $(cat "$SA/token")" -H "Content-Type: application/merge-patch+json" -d "$PATCH" "https://kubernetes.default.svc/api/v1/namespaces/${var.namespace}/secrets/ecr-registry")
                if [ "$status" != "200" ]; then cat /tmp/response >&2; exit 1; fi
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
