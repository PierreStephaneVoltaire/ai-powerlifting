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
}

resource "kubernetes_service_account_v1" "reference_litellm" {
  metadata {
    name      = "reference-litellm"
    namespace = var.namespace
  }
}

resource "kubernetes_deployment_v1" "reference_litellm" {
  depends_on = [kubectl_manifest.reference_litellm_l4, kubectl_manifest.reference_litellm_callers]

  metadata {
    name      = "reference-litellm"
    namespace = var.namespace
  }
  spec {
    replicas = 1
    selector { match_labels = { app = "reference-litellm" } }
    template {
      metadata {
        labels      = { app = "reference-litellm", "istio.io/dataplane-mode" = "ambient" }
        annotations = { "checksum/config" = sha256(kubernetes_config_map_v1.reference_litellm.data["config.yaml"]) }
      }
      spec {
        service_account_name = kubernetes_service_account_v1.reference_litellm.metadata[0].name
        container {
          name    = "litellm"
          image   = var.litellm_image
          command = ["/bin/sh", "-c"]
          args    = ["exec litellm --config /etc/litellm/config.yaml --port 4000 >/dev/null 2>&1"]
          env_from {
            secret_ref { name = kubernetes_secret_v1.reference_litellm.metadata[0].name }
          }
          port { container_port = 4000 }
          resources {
            requests = { cpu = "100m", memory = "512Mi" }
            limits   = { cpu = "1", memory = "2Gi" }
          }
          readiness_probe {
            tcp_socket { port = 4000 }
            initial_delay_seconds = 5
            period_seconds        = 10
          }
          volume_mount {
            name       = "config"
            mount_path = "/etc/litellm"
            read_only  = true
          }
        }
        volume {
          name = "config"
          config_map { name = kubernetes_config_map_v1.reference_litellm.metadata[0].name }
        }
      }
    }
  }
  lifecycle {
    precondition {
      condition     = alltrue([for name in local.reference_providers : var.litellm_providers[name].type == "openrouter" && contains(local.litellm_key_names, name)])
      error_message = "Reference models require OpenRouter providers with configured credentials."
    }
  }
}

resource "kubernetes_service_v1" "reference_litellm" {
  metadata {
    name      = "reference-litellm"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }
  spec {
    selector = { app = "reference-litellm" }
    port {
      port        = 4000
      target_port = 4000
      name        = "http"
    }
  }
}

resource "kubectl_manifest" "reference_litellm_l4" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "reference-litellm-waypoint-only", namespace = var.namespace }
    spec = {
      selector = { matchLabels = { app = "reference-litellm" } }
      action   = "ALLOW"
      rules    = [{ from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/nolift-waypoint"] } }] }]
    }
  })
  depends_on = [kubectl_manifest.strict_mtls, kubectl_manifest.portal_waypoint]
}

resource "kubectl_manifest" "reference_litellm_callers" {
  yaml_body = yamlencode({
    apiVersion = "security.istio.io/v1"
    kind       = "AuthorizationPolicy"
    metadata   = { name = "reference-litellm-assistant-only", namespace = var.namespace }
    spec = {
      targetRefs = [{ group = "", kind = "Service", name = kubernetes_service_v1.reference_litellm.metadata[0].name }]
      action     = "ALLOW"
      rules = [{
        from = [{ source = { principals = ["cluster.local/ns/${var.namespace}/sa/pl-assistant"] } }]
        to   = [{ operation = { ports = ["4000"], methods = ["POST"], paths = ["/v1/embeddings", "/v1/chat/completions"] } }]
      }]
    }
  })
  depends_on = [kubectl_manifest.portal_waypoint, kubectl_manifest.strict_mtls]
}
