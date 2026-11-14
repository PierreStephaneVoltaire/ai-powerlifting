data "aws_ssm_parameter" "litellm_master_key" {
  name            = "/powerlifting/litellm/master_key"
  with_decryption = true
}

resource "kubernetes_secret_v1" "provider_keys" {
  metadata {
    name      = "pl-coach-provider-keys"
    namespace = var.namespace
  }

  data = {
    COACH_PROVIDER_KEYS = jsonencode(merge(var.coach_provider_api_keys, {
      litellm = data.aws_ssm_parameter.litellm_master_key.value
    }))
  }
}
