resource "kubernetes_secret_v1" "provider_keys" {
  metadata {
    name      = "pl-coach-provider-keys"
    namespace = var.namespace
  }

  data = {
    COACH_PROVIDER_KEYS = jsonencode(var.coach_provider_api_keys)
  }
}
