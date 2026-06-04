locals {
  if_test_namespace = "if-portals-test"
  if_test_model_id  = "deepseek/deepseek-v4-flash"

  if_agent_api_test_model_env = {
    LLM_BASE_URL = "https://openrouter.ai/api/v1"

    API_MODEL_NAME  = local.if_test_model_id
    TOKENIZER_MODEL = var.tokenizer_model
    EMBEDDING_MODEL = var.embedding_model

    SUGGESTION_MODEL        = local.if_test_model_id
    SCORING_MODELS          = local.if_test_model_id
    TOPIC_SHIFT_MODEL       = local.if_test_model_id
    DIRECTIVE_REWRITE_MODEL = local.if_test_model_id
    CONDENSER_MODEL         = local.if_test_model_id
    CONDENSE_INTENT_MODEL   = local.if_test_model_id
    PRESET_FALLBACK_MODEL   = local.if_test_model_id
    MODEL_ROUTER_MODEL      = local.if_test_model_id
    HEALTH_HELPER_MODEL     = local.if_test_model_id

    OPENCODE_PLANNER_MODEL  = local.if_test_model_id
    IF_DEFAULT_DIRECT_MODEL = local.if_test_model_id

    HEARTBEAT_FALLBACK_MODEL = local.if_test_model_id
    REFLECTION_MODEL         = local.if_test_model_id
    RESEARCH_AGENT_MODEL     = local.if_test_model_id
    DIARY_SIGNAL_MODEL       = local.if_test_model_id

    ANALYSIS_MODEL      = local.if_test_model_id
    ESTIMATE_MODEL      = local.if_test_model_id
    GLOSSARY_TEXT_MODEL = local.if_test_model_id
    IMPORT_FAST_MODEL   = local.if_test_model_id

    TIER_UPGRADE_THRESHOLD = tostring(var.tier_upgrade_threshold)
    TIER_AIR_LIMIT         = tostring(var.tier_air_limit)
    TIER_STANDARD_LIMIT    = tostring(var.tier_standard_limit)
    TIER_HEAVY_LIMIT       = tostring(var.tier_heavy_limit)
    TIER_AIR_PRESET        = var.tier_air_preset
    TIER_STANDARD_PRESET   = var.tier_standard_preset
    TIER_HEAVY_PRESET      = var.tier_heavy_preset

    SPECIALIST_PRESET           = var.specialist_preset
    SPECIALIST_MAX_TURNS        = tostring(var.specialist_max_turns)
    SPECIALIST_REASONING_EFFORT = "low"
    THINKING_PRESET             = var.thinking_preset
    THINKING_MAX_TURNS          = tostring(var.thinking_max_turns)

    ORCHESTRATOR_SUBAGENT_MODEL     = local.if_test_model_id
    ORCHESTRATOR_ANALYSIS_MODEL     = local.if_test_model_id
    ORCHESTRATOR_SYNTHESIS_MODEL    = local.if_test_model_id
    ORCHESTRATOR_MAX_TURNS          = tostring(var.orchestrator_max_turns)
    ORCHESTRATOR_ANALYSIS_MAX_TURNS = tostring(var.orchestrator_analysis_max_turns)

    LLM_REASONING_EFFORT                 = "low"
    ESTIMATE_MODEL_REASONING_EFFORT      = "low"
    ESTIMATE_MODEL_VERBOSITY             = "low"
    HEALTH_HELPER_MODEL_REASONING_EFFORT = "low"
    HEALTH_HELPER_MODEL_VERBOSITY        = "low"
    ANALYSIS_MODEL_THINKING_BUDGET       = "1024"

    MODEL_ROUTER_ENABLED         = "true"
    MODEL_STATS_REFRESH_INTERVAL = "1800"
    MODEL_SEED_INTERVAL          = "3600"
  }
}

resource "kubernetes_namespace" "if_portals_test" {
  metadata {
    name = local.if_test_namespace
    labels = {
      app         = "if-ecosystem-test"
      environment = "test"
      managed-by  = "terraform"
    }
  }
}

resource "kubernetes_secret" "ecr_registry_test" {
  metadata {
    name      = "ecr-registry"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = {
    ".dockerconfigjson" = local.ecr_dockerconfigjson
  }

  type = "kubernetes.io/dockerconfigjson"
}

resource "kubernetes_secret" "if_agent_api_secrets_test" {
  metadata {
    name      = "if-agent-api-secrets"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = {
    OPENROUTER_API_KEY = var.openrouter_api_key
    DISCORD_TOKEN      = var.discord_token
  }

  type = "Opaque"
}

resource "kubernetes_service_account" "if_agent_api_test" {
  metadata {
    name      = "if-agent-api"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
    labels = {
      app         = "if-agent-api"
      environment = "test"
      managed-by  = "terraform"
    }
  }

  automount_service_account_token = true
}

resource "kubernetes_role" "terminal_manager_test" {
  metadata {
    name      = "terminal-manager"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  rule {
    api_groups = [""]
    resources  = ["pods"]
    verbs      = ["get", "list", "watch", "create", "delete", "patch"]
  }

  rule {
    api_groups = [""]
    resources  = ["pods/log", "pods/status"]
    verbs      = ["get"]
  }

  rule {
    api_groups = [""]
    resources  = ["persistentvolumeclaims"]
    verbs      = ["get", "list", "create", "delete"]
  }
}

resource "kubernetes_role_binding" "terminal_manager_test" {
  metadata {
    name      = "terminal-manager"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  subject {
    kind      = "ServiceAccount"
    name      = kubernetes_service_account.if_agent_api_test.metadata[0].name
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  role_ref {
    kind      = "Role"
    name      = kubernetes_role.terminal_manager_test.metadata[0].name
    api_group = "rbac.authorization.k8s.io"
  }
}

resource "kubernetes_config_map" "if_agent_api_test_config" {
  metadata {
    name      = "if-agent-api-config"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = {
    IF_CORE_TABLE_NAME               = var.dynamodb_core_table
    IF_HEALTH_TABLE_NAME             = var.dynamodb_health_table
    IF_TEMPLATES_TABLE_NAME          = var.dynamodb_templates_table
    IF_TEMPLATES_LIBRARY_PK          = "test"
    IF_SESSIONS_TABLE_NAME           = var.dynamodb_sessions_table
    ANALYSIS_CACHE_TABLE_NAME        = var.dynamodb_analysis_cache_table
    IF_FINANCE_TABLE_NAME            = var.dynamodb_finance_table
    IF_DIARY_ENTRIES_TABLE_NAME      = var.dynamodb_diary_entries_table
    IF_DIARY_SIGNALS_TABLE_NAME      = var.dynamodb_diary_signals_table
    IF_PROPOSALS_TABLE_NAME          = var.dynamodb_proposals_table
    IF_MODELS_TABLE_NAME             = var.dynamodb_models_table
    IF_MODELS_TABLE_NAME             = var.dynamodb_models_table
    IF_EXECUTION_REGISTRY_TABLE_NAME = var.dynamodb_execution_registry_table
    POWERLIFTING_S3_BUCKET           = aws_s3_bucket.powerlifting_data.id
    SPECIALISTS_PATH                 = var.specialists_path
    EXTERNAL_TOOLS_PATH              = var.tools_path
    MODELS_PATH                      = "/app/test-models"
    SCRIPTS_PATH                     = var.scripts_path

    CONTEXT_CONDENSE_THRESHOLD = tostring(var.context_condense_threshold)
    MESSAGE_WINDOW             = tostring(var.message_window)
    TOOL_OUTPUT_CHAR_LIMIT     = tostring(var.tool_output_char_limit)

    HOST = "0.0.0.0"
    PORT = "8000"

    CHANNEL_DEBOUNCE_SECONDS = tostring(var.channel_debounce_seconds)
    CHANNEL_MAX_CHUNK_CHARS  = tostring(var.channel_max_chunk_chars)

    HEARTBEAT_ENABLED        = "false"
    HEARTBEAT_IDLE_HOURS     = tostring(var.heartbeat_idle_hours)
    HEARTBEAT_COOLDOWN_HOURS = tostring(var.heartbeat_cooldown_hours)
    HEARTBEAT_QUIET_HOURS    = var.heartbeat_quiet_hours

    REFLECTION_CONTEXT_ID               = "test"
    REFLECTION_ENABLED                  = "false"
    REFLECTION_PERIODIC_HOURS           = tostring(var.reflection_periodic_hours)
    REFLECTION_POST_SESSION_MIN_TURNS   = tostring(var.reflection_post_session_min_turns)
    REFLECTION_THRESHOLD_UNCATEGORIZED  = tostring(var.reflection_threshold_uncategorized)
    HEALTH_PROGRAM_PK                   = "test"
    IF_USER_PK                          = "test"
    DIARY_TTL_DAYS                      = tostring(var.diary_ttl_days)
    DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS = tostring(var.diary_signal_compute_interval_hours)

    AWS_REGION = var.region
    LOG_LEVEL  = var.log_level
  }
}

resource "kubernetes_config_map" "if_agent_api_test_model_config" {
  metadata {
    name      = "if-agent-api-model-config"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = local.if_agent_api_test_model_env
}

resource "kubernetes_config_map" "if_agent_api_test_model_allowlist" {
  metadata {
    name      = "if-agent-api-model-allowlist"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = {
    "model_ids.txt"            = "${local.if_test_model_id}\n"
    "model_selection_rules.md" = <<-EOT
      # Test Model Selection Rules

      This private test namespace intentionally exposes only cheap test models.

      - The planner must choose `${local.if_test_model_id}` for every route in `if-portals-test`.
      - Do not choose production-quality, expensive, online, or provider-specific fallback models in this namespace.
      - If a prompt asks for powerlifting, technical, or research work, still use `${local.if_test_model_id}` because `model_ids.txt` is the hard allowlist for tests.
    EOT
  }
}

resource "kubernetes_config_map" "powerlifting_app_test_config" {
  metadata {
    name      = "powerlifting-app-config"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  data = {
    AWS_REGION                  = var.region
    DYNAMODB_TABLE              = var.dynamodb_powerlifting_table
    IF_USER_TABLE               = var.dynamodb_user_table
    IF_SESSIONS_TABLE_NAME      = var.dynamodb_sessions_table
    ANALYSIS_CACHE_TABLE_NAME   = var.dynamodb_analysis_cache_table
    NODE_ENV                    = "production"
    PORT                        = "3005"
    FRONTEND_URL                = "http://localhost:3001"
    IF_API_URL                  = "http://if-agent-api:8000"
    AGENT_MODEL                 = local.if_test_model_id
    POWERLIFTING_TEST_MAPPED_PK = "test"
    DISCORD_CLIENT_ID           = var.discord_client_id
    DISCORD_CLIENT_SECRET       = var.discord_client_secret
    DISCORD_REDIRECT_URI        = "http://localhost:3005/api/auth/discord/callback"
    JWT_SECRET                  = var.jwt_secret
    COOKIE_DOMAIN               = ""
    COOKIE_SECURE               = "false"
  }
}

resource "kubernetes_deployment" "if_agent_api_test" {
  metadata {
    name      = "if-agent-api"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
    labels = {
      app         = "if-agent-api"
      environment = "test"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "if-agent-api"
      }
    }

    template {
      metadata {
        labels = {
          app         = "if-agent-api"
          environment = "test"
        }
        annotations = {
          "checksum/config"          = sha1(jsonencode(kubernetes_config_map.if_agent_api_test_config.data))
          "checksum/model-config"    = sha1(jsonencode(kubernetes_config_map.if_agent_api_test_model_config.data))
          "checksum/model-allowlist" = sha1(jsonencode(kubernetes_config_map.if_agent_api_test_model_allowlist.data))
        }
      }

      spec {
        service_account_name = kubernetes_service_account.if_agent_api_test.metadata[0].name

        image_pull_secrets {
          name = kubernetes_secret.ecr_registry_test.metadata[0].name
        }

        volume {
          name = "data-storage"
          empty_dir {}
        }

        volume {
          name = "sandbox-storage"
          empty_dir {}
        }

        volume {
          name = "conversations-storage"
          empty_dir {}
        }

        volume {
          name = "facts-storage"
          empty_dir {}
        }

        volume {
          name = "aws-credentials"
          host_path {
            path = var.aws_credentials_host_path
            type = "Directory"
          }
        }

        volume {
          name = "tools-directory"
          host_path {
            path = var.tools_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "specialists-directory"
          host_path {
            path = var.specialists_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "scripts-directory"
          host_path {
            path = var.scripts_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "skills-directory"
          host_path {
            path = var.skills_host_path
            type = "DirectoryOrCreate"
          }
        }

        volume {
          name = "test-model-allowlist"
          config_map {
            name = kubernetes_config_map.if_agent_api_test_model_allowlist.metadata[0].name
          }
        }

        container {
          name              = "api"
          image             = "${aws_ecr_repository.if_agent_api.repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 8000
          }

          resources {
            limits = {
              memory = "${var.api_memory_mb}Mi"
              cpu    = "${var.api_cpu_millicores}m"
            }
            requests = {
              memory = "${var.api_memory_request_mb}Mi"
              cpu    = "${var.api_cpu_request_millicores}m"
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.if_agent_api_test_config.metadata[0].name
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.if_agent_api_test_model_config.metadata[0].name
            }
          }

          env_from {
            secret_ref {
              name = kubernetes_secret.if_agent_api_secrets_test.metadata[0].name
            }
          }

          volume_mount {
            name       = "data-storage"
            mount_path = "/app/src/data"
          }

          volume_mount {
            name       = "sandbox-storage"
            mount_path = "/app/src/sandbox"
          }

          volume_mount {
            name       = "conversations-storage"
            mount_path = "/app/src/data/conversations"
          }

          volume_mount {
            name       = "facts-storage"
            mount_path = "/app/src/data/facts"
          }

          volume_mount {
            name       = "aws-credentials"
            mount_path = "/root/.aws"
            read_only  = true
          }

          volume_mount {
            name       = "tools-directory"
            mount_path = "/app/tools"
            read_only  = true
          }

          volume_mount {
            name       = "specialists-directory"
            mount_path = "/app/specialists"
            read_only  = true
          }

          volume_mount {
            name       = "scripts-directory"
            mount_path = "/app/scripts"
            read_only  = true
          }

          volume_mount {
            name       = "skills-directory"
            mount_path = "/app/skills"
            read_only  = true
          }

          volume_mount {
            name       = "test-model-allowlist"
            mount_path = "/app/test-models"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 120
            timeout_seconds       = 30
            failure_threshold     = 3
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 8000
            }
            initial_delay_seconds = 30
            period_seconds        = 60
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build_main_api]
}

resource "kubernetes_deployment" "powerlifting_app_backend_test" {
  metadata {
    name      = "powerlifting-app-backend"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
    labels = {
      app         = "powerlifting-app-backend"
      environment = "test"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "powerlifting-app-backend"
      }
    }

    template {
      metadata {
        labels = {
          app         = "powerlifting-app-backend"
          environment = "test"
        }
        annotations = {
          "prometheus.io/scrape" = "true"
          "prometheus.io/port"   = "3005"
          "prometheus.io/path"   = "/metrics"
          "checksum/config"      = nonsensitive(sha1(jsonencode(kubernetes_config_map.powerlifting_app_test_config.data)))
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.ecr_registry_test.metadata[0].name
        }

        volume {
          name = "aws-credentials"
          host_path {
            path = var.aws_credentials_host_path
            type = "Directory"
          }
        }

        container {
          name              = "backend"
          image             = "${aws_ecr_repository.portal_backends["powerlifting-app-backend"].repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 3005
          }

          resources {
            limits = {
              memory = "${var.portal_memory_mb}Mi"
              cpu    = "${var.portal_cpu_millicores}m"
            }
            requests = {
              memory = "${var.portal_memory_mb / 2}Mi"
              cpu    = "${var.portal_cpu_millicores / 2}m"
            }
          }

          env_from {
            config_map_ref {
              name = kubernetes_config_map.powerlifting_app_test_config.metadata[0].name
            }
          }

          volume_mount {
            name       = "aws-credentials"
            mount_path = "/root/.aws"
            read_only  = true
          }

          liveness_probe {
            http_get {
              path = "/health"
              port = 3005
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/health"
              port = 3005
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }

  depends_on = [null_resource.packer_build_portal_backends["powerlifting-app"]]
}

resource "kubernetes_deployment" "powerlifting_app_frontend_test" {
  metadata {
    name      = "powerlifting-app-frontend"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
    labels = {
      app         = "powerlifting-app-frontend"
      environment = "test"
    }
  }

  spec {
    replicas = 1

    selector {
      match_labels = {
        app = "powerlifting-app-frontend"
      }
    }

    template {
      metadata {
        labels = {
          app         = "powerlifting-app-frontend"
          environment = "test"
        }
      }

      spec {
        image_pull_secrets {
          name = kubernetes_secret.ecr_registry_test.metadata[0].name
        }

        container {
          name              = "frontend"
          image             = "${aws_ecr_repository.portal_frontends["powerlifting-app-frontend"].repository_url}:latest"
          image_pull_policy = "Always"

          port {
            container_port = 3001
          }

          resources {
            limits = {
              memory = "${var.frontend_memory_mb}Mi"
              cpu    = "${var.frontend_cpu_millicores}m"
            }
            requests = {
              memory = "${var.frontend_memory_mb / 2}Mi"
              cpu    = "${var.frontend_cpu_millicores / 2}m"
            }
          }

          liveness_probe {
            http_get {
              path = "/"
              port = 3001
            }
            initial_delay_seconds = 10
            period_seconds        = 10
          }

          readiness_probe {
            http_get {
              path = "/"
              port = 3001
            }
            initial_delay_seconds = 5
            period_seconds        = 5
          }
        }
      }
    }
  }

  depends_on = [
    null_resource.packer_build_portal_frontends["powerlifting-app"],
    kubernetes_deployment.powerlifting_app_backend_test,
  ]
}

resource "kubernetes_service" "if_agent_api_test" {
  metadata {
    name      = "if-agent-api"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  spec {
    selector = {
      app = "if-agent-api"
    }

    port {
      port        = 8000
      target_port = 8000
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_service" "powerlifting_app_backend_test" {
  metadata {
    name      = "powerlifting-app-backend"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  spec {
    selector = {
      app = "powerlifting-app-backend"
    }

    port {
      port        = 3005
      target_port = 3005
    }

    type = "ClusterIP"
  }
}

resource "kubernetes_service" "powerlifting_app_frontend_test" {
  metadata {
    name      = "powerlifting-app-frontend"
    namespace = kubernetes_namespace.if_portals_test.metadata[0].name
  }

  spec {
    selector = {
      app = "powerlifting-app-frontend"
    }

    port {
      port        = 3001
      target_port = 3001
    }

    type = "ClusterIP"
  }
}
