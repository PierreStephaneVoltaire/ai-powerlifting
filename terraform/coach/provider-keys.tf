data "aws_secretsmanager_secret_version" "litellm" {
  secret_id = "powerlifting/litellm"
}

resource "kubernetes_secret_v1" "provider_keys" {
  metadata {
    name      = "pl-coach-provider-keys"
    namespace = var.namespace
  }

  data = {
    COACH_PROVIDER_KEYS = jsonencode(merge(var.coach_provider_api_keys, {
      litellm = jsondecode(data.aws_secretsmanager_secret_version.litellm.secret_string).master_key
    }))
  }
}
