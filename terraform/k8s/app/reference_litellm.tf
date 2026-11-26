locals {
  reference_model_names = ["pl-strong", "pl-embed"]
  reference_providers = toset(flatten([
    for alias in local.reference_model_names : [for deployment in var.litellm_models[alias] : deployment.provider]
  ]))
  reference_config = {
    model_list = flatten([for alias in local.reference_model_names : [for deployment in var.litellm_models[alias] : {
      model_name = alias
      model_info = {
        mode                                = coalesce(deployment.mode, "responses")
        configurable_clientside_auth_params = ["turn_off_message_logging"]
      }
      litellm_params = {
        model                   = "openrouter/${deployment.model}"
        litellm_credential_name = deployment.provider
        extra_body              = { provider = { zdr = true, data_collection = "deny" } }
      }
    }]])
    credential_list = [for credential in local.litellm_credentials : credential if contains(local.reference_providers, credential.credential_name)]
    general_settings = {
      master_key         = "os.environ/LITELLM_MASTER_KEY"
      disable_spend_logs = true
      disable_error_logs = true
    }
    litellm_settings = {
      turn_off_message_logging      = true
      redact_messages_in_exceptions = true
    }
  }
}

resource "random_password" "reference_litellm" {
  length  = 64
  special = false
}

resource "kubernetes_secret_v1" "reference_litellm" {
  metadata {
    name      = "reference-litellm-credentials"
    namespace = var.namespace
  }
  data = merge(
    { LITELLM_MASTER_KEY = "sk-${random_password.reference_litellm.result}" },
    { for name in local.reference_providers : local.litellm_env_names[name] => local.litellm_provider_keys[name] },
  )
}

resource "kubernetes_config_map_v1" "reference_litellm" {
  metadata {
    name      = "reference-litellm-config"
    namespace = var.namespace
  }
  data = { "config.yaml" = yamlencode(local.reference_config) }
  lifecycle {
    precondition {
      condition     = alltrue([for name in local.reference_providers : var.litellm_providers[name].type == "openrouter" && contains(local.litellm_key_names, name)])
      error_message = "Reference models require OpenRouter providers with configured credentials."
    }
  }
}
