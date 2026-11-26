resource "kubernetes_secret_v1" "prompt_cache_api" {
  metadata {
    name      = "pl-prompt-cache-api"
    namespace = var.namespace
  }

  data = {
    OPENAI_API_KEY = lookup(local.litellm_provider_keys, "openai", "")
  }
}
