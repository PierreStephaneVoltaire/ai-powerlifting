variable "litellm_providers" {
  type = map(object({
    type     = string
    base_url = optional(string)
  }))

  validation {
    condition     = alltrue([for provider in values(var.litellm_providers) : contains(["chatgpt", "openrouter", "openai"], provider.type)])
    error_message = "litellm_providers type must be chatgpt, openrouter or openai."
  }
}

variable "litellm_models" {
  type = map(list(object({
    provider = string
    model    = string
    weight   = optional(number)
  })))

  validation {
    condition     = alltrue(flatten([for deployments in values(var.litellm_models) : [for deployment in deployments : contains(keys(var.litellm_providers), deployment.provider)]]))
    error_message = "Every litellm_models deployment provider must exist in litellm_providers."
  }
}

variable "litellm_fallbacks" {
  type    = map(list(string))
  default = {}

  validation {
    condition     = alltrue(flatten([for alias, targets in var.litellm_fallbacks : concat([contains(keys(var.litellm_models), alias)], [for target in targets : contains(keys(var.litellm_models), target)])]))
    error_message = "litellm_fallbacks must only reference aliases defined in litellm_models."
  }
}

variable "litellm_image" {
  type    = string
  default = "ghcr.io/berriai/litellm:v1.108.8"
}

data "aws_secretsmanager_secret_version" "litellm" {
  secret_id = "powerlifting/litellm"
}

locals {
  litellm_secret = jsondecode(data.aws_secretsmanager_secret_version.litellm.secret_string)

  litellm_key_names = nonsensitive(keys(local.litellm_secret.provider_keys))

  litellm_env_names = { for name in local.litellm_key_names : name => "${upper(replace(name, "-", "_"))}_API_KEY" }

  litellm_credentials = [
    for name, provider in var.litellm_providers : {
      credential_name = name
      credential_values = merge(
        contains(local.litellm_key_names, name) ? { api_key = "os.environ/${local.litellm_env_names[name]}" } : {},
        provider.base_url != null ? { api_base = provider.base_url } : {},
      )
    } if contains(local.litellm_key_names, name) || provider.base_url != null
  ]

  litellm_config = merge(
    {
      model_list = flatten([for alias, deployments in var.litellm_models : [for deployment in deployments : {
        model_name = alias
        model_info = { mode = "responses" }
        litellm_params = merge(
          { model = "${var.litellm_providers[deployment.provider].type}/${deployment.model}" },
          var.litellm_providers[deployment.provider].type == "chatgpt" ? {} : { litellm_credential_name = deployment.provider },
          deployment.weight != null ? { weight = deployment.weight } : {},
        )
      }]])
      general_settings = { master_key = "os.environ/LITELLM_MASTER_KEY" }
    },
    length(local.litellm_credentials) > 0 ? { credential_list = local.litellm_credentials } : {},
    length(var.litellm_fallbacks) > 0 ? { router_settings = { fallbacks = [for alias, targets in var.litellm_fallbacks : { (alias) = targets }] } } : {},
  )
}

resource "kubernetes_secret_v1" "litellm" {
  metadata {
    name      = "litellm-keys"
    namespace = var.namespace
  }

  data = merge(
    { LITELLM_MASTER_KEY = local.litellm_secret.master_key },
    { for name in local.litellm_key_names : local.litellm_env_names[name] => local.litellm_secret.provider_keys[name] },
  )
}

resource "kubernetes_config_map_v1" "litellm" {
  metadata {
    name      = "litellm-config"
    namespace = var.namespace
  }

  data = {
    "config.yaml" = yamlencode(local.litellm_config)
  }
}

resource "kubernetes_persistent_volume_claim_v1" "litellm" {
  metadata {
    name      = "litellm-chatgpt-token"
    namespace = var.namespace
  }

  spec {
    access_modes       = ["ReadWriteOnce"]
    storage_class_name = var.storage_class

    resources {
      requests = { storage = "1Gi" }
    }
  }

  wait_until_bound = false
}

resource "kubernetes_deployment_v1" "litellm" {
  depends_on       = [kubectl_manifest.l4_waypoint_only, kubectl_manifest.service_callers, kubectl_manifest.strict_mtls]
  wait_for_rollout = false

  metadata {
    name      = "litellm"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    replicas = 1

    strategy {
      type = "Recreate"
    }

    selector {
      match_labels = { app = "litellm" }
    }

    template {
      metadata {
        labels      = { app = "litellm", "istio.io/dataplane-mode" = "ambient" }
        annotations = { "checksum/config" = sha256(kubernetes_config_map_v1.litellm.data["config.yaml"]) }
      }

      spec {
        service_account_name             = "litellm"
        automount_service_account_token  = false
        enable_service_links             = false
        termination_grace_period_seconds = 30

        container {
          name              = "litellm"
          image             = var.litellm_image
          image_pull_policy = "IfNotPresent"
          args              = ["--config", "/etc/litellm/config.yaml", "--port", "4000"]

          env {
            name  = "CHATGPT_TOKEN_DIR"
            value = "/data/chatgpt"
          }

          env_from {
            secret_ref {
              name = kubernetes_secret_v1.litellm.metadata[0].name
            }
          }

          port {
            container_port = 4000
            name           = "http"
            protocol       = "TCP"
          }

          resources {
            limits   = { cpu = "1", memory = "1Gi" }
            requests = { cpu = "50m", memory = "256Mi" }
          }

          readiness_probe {
            http_get {
              path = "/health/liveliness"
              port = 4000
            }
            initial_delay_seconds = 20
            period_seconds        = 10
          }

          liveness_probe {
            http_get {
              path = "/health/liveliness"
              port = 4000
            }
            initial_delay_seconds = 60
            period_seconds        = 20
          }

          volume_mount {
            name       = "config"
            mount_path = "/etc/litellm"
            read_only  = true
          }

          volume_mount {
            name       = "chatgpt-token"
            mount_path = "/data/chatgpt"
          }
        }

        volume {
          name = "config"

          config_map {
            name = kubernetes_config_map_v1.litellm.metadata[0].name
          }
        }

        volume {
          name = "chatgpt-token"

          persistent_volume_claim {
            claim_name = kubernetes_persistent_volume_claim_v1.litellm.metadata[0].name
          }
        }
      }
    }
  }
}

resource "kubernetes_service_v1" "litellm" {
  metadata {
    name      = "litellm"
    namespace = var.namespace
    labels    = { "istio.io/use-waypoint" = "nolift-waypoint" }
  }

  spec {
    selector = { app = "litellm" }

    port {
      port        = 4000
      target_port = 4000
      name        = "http"
      protocol    = "TCP"
    }
  }
}
