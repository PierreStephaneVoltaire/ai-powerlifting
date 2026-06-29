resource "kubernetes_secret" "pl_fission_secrets" {
  count = var.fission_powerlifting_env_enabled ? 1 : 0

  metadata {
    name      = "pl-fission-secrets"
    namespace = var.fission_powerlifting_function_namespace
  }

  data = {
    INTERNAL_API_TOKEN = var.pl_internal_token
    OPENROUTER_API_KEY = var.openrouter_api_key
  }
}
