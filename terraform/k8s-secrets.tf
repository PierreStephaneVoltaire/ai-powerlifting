data "aws_ecr_authorization_token" "private" {}

locals {
  ecr_registry_server  = replace(data.aws_ecr_authorization_token.private.proxy_endpoint, "https://", "")
  ecr_registry_auth    = base64encode("${data.aws_ecr_authorization_token.private.user_name}:${data.aws_ecr_authorization_token.private.password}")
  ecr_dockerconfigjson = <<-EOT
{
  "auths": {
    "${local.ecr_registry_server}": {
      "username": "${data.aws_ecr_authorization_token.private.user_name}",
      "password": "${data.aws_ecr_authorization_token.private.password}",
      "email": "none",
      "auth": "${local.ecr_registry_auth}"
    }
  }
}
EOT
}

resource "kubernetes_secret" "ecr_registry" {
  metadata {
    name      = "ecr-registry"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    ".dockerconfigjson" = local.ecr_dockerconfigjson
  }

  type = "kubernetes.io/dockerconfigjson"
}

resource "kubernetes_secret" "if_agent_api_secrets" {
  metadata {
    name      = "if-agent-api-secrets"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    OPENROUTER_API_KEY = var.openrouter_api_key
    DISCORD_TOKEN      = var.discord_token
    GITHUB_TOKEN       = var.github_token
  }

  type = "Opaque"
}

resource "kubernetes_config_map" "if_agent_api_config" {
  metadata {
    name      = "if-agent-api-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    IF_CORE_TABLE_NAME               = var.dynamodb_core_table
    IF_HEALTH_TABLE_NAME             = var.dynamodb_health_table
    IF_TEMPLATES_TABLE_NAME          = var.dynamodb_templates_table
    IF_TEMPLATES_LIBRARY_PK          = "template_library"
    IF_SESSIONS_TABLE_NAME           = var.dynamodb_sessions_table
    ANALYSIS_CACHE_TABLE_NAME        = var.dynamodb_analysis_cache_table
    IF_FINANCE_TABLE_NAME            = var.dynamodb_finance_table
    IF_DIARY_ENTRIES_TABLE_NAME      = var.dynamodb_diary_entries_table
    IF_DIARY_SIGNALS_TABLE_NAME      = var.dynamodb_diary_signals_table
    IF_PROPOSALS_TABLE_NAME          = var.dynamodb_proposals_table
    IF_MODELS_TABLE_NAME             = var.dynamodb_models_table
    IF_EXECUTION_REGISTRY_TABLE_NAME = var.dynamodb_execution_registry_table
    POWERLIFTING_S3_BUCKET           = aws_s3_bucket.powerlifting_data.id
    SPECIALISTS_PATH                 = var.specialists_path
    EXTERNAL_TOOLS_PATH              = var.tools_path
    MODELS_PATH                      = var.models_path
    SCRIPTS_PATH                     = var.scripts_path

    CONTEXT_CONDENSE_THRESHOLD = tostring(var.context_condense_threshold)
    MESSAGE_WINDOW             = tostring(var.message_window)
    TOOL_OUTPUT_CHAR_LIMIT     = tostring(var.tool_output_char_limit)

    HOST = "0.0.0.0"
    PORT = "8000"

    CHANNEL_DEBOUNCE_SECONDS = tostring(var.channel_debounce_seconds)
    CHANNEL_MAX_CHUNK_CHARS  = tostring(var.channel_max_chunk_chars)

    HEARTBEAT_ENABLED        = tostring(var.heartbeat_enabled)
    HEARTBEAT_IDLE_HOURS     = tostring(var.heartbeat_idle_hours)
    HEARTBEAT_COOLDOWN_HOURS = tostring(var.heartbeat_cooldown_hours)
    HEARTBEAT_QUIET_HOURS    = var.heartbeat_quiet_hours

    REFLECTION_ENABLED                 = tostring(var.reflection_enabled)
    REFLECTION_PERIODIC_HOURS          = tostring(var.reflection_periodic_hours)
    REFLECTION_POST_SESSION_MIN_TURNS  = tostring(var.reflection_post_session_min_turns)
    REFLECTION_THRESHOLD_UNCATEGORIZED = tostring(var.reflection_threshold_uncategorized)

    HEALTH_PROGRAM_PK = var.health_program_pk

    IF_USER_PK = var.if_user_pk

    DIARY_TTL_DAYS                      = tostring(var.diary_ttl_days)
    DIARY_SIGNAL_COMPUTE_INTERVAL_HOURS = tostring(var.diary_signal_compute_interval_hours)

    AWS_REGION = var.region

    LOG_LEVEL = var.log_level
  }
}

resource "kubernetes_config_map" "if_agent_api_model_config" {
  metadata {
    name      = "if-agent-api-model-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = merge({
    API_MODEL_NAME  = var.api_model_name
    TOKENIZER_MODEL = var.tokenizer_model
    EMBEDDING_MODEL = var.embedding_model

    SUGGESTION_MODEL        = var.suggestion_model
    DIRECTIVE_REWRITE_MODEL = var.directive_rewrite_model
    CONDENSER_MODEL         = var.condenser_model
    REFLECTION_MODEL        = var.reflection_model
    RESEARCH_AGENT_MODEL    = var.research_agent_model
    DIARY_SIGNAL_MODEL      = var.diary_signal_model
    MODEL_ROUTER_MODEL      = var.model_router_model
    HEALTH_HELPER_MODEL     = var.health_helper_model

    TIER_UPGRADE_THRESHOLD = tostring(var.tier_upgrade_threshold)
    TIER_AIR_LIMIT         = tostring(var.tier_air_limit)
    TIER_STANDARD_LIMIT    = tostring(var.tier_standard_limit)
    TIER_HEAVY_LIMIT       = tostring(var.tier_heavy_limit)
    TIER_AIR_PRESET        = var.tier_air_preset
    TIER_STANDARD_PRESET   = var.tier_standard_preset
    TIER_HEAVY_PRESET      = var.tier_heavy_preset

    SPECIALIST_PRESET    = var.specialist_preset
    SPECIALIST_MAX_TURNS = tostring(var.specialist_max_turns)
    THINKING_PRESET      = var.thinking_preset
    THINKING_MAX_TURNS   = tostring(var.thinking_max_turns)

    ORCHESTRATOR_SUBAGENT_MODEL     = var.orchestrator_subagent_model
    ORCHESTRATOR_ANALYSIS_MODEL     = var.orchestrator_analysis_model
    ORCHESTRATOR_SYNTHESIS_MODEL    = var.orchestrator_synthesis_model
    ORCHESTRATOR_MAX_TURNS          = tostring(var.orchestrator_max_turns)
    ORCHESTRATOR_ANALYSIS_MAX_TURNS = tostring(var.orchestrator_analysis_max_turns)

    LLM_REASONING_EFFORT = var.llm_reasoning_effort
  }, var.if_agent_api_model_env)
}

resource "kubernetes_config_map" "main_portal_config" {
  metadata {
    name      = "main-portal-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    NODE_ENV              = "production"
    PORT                  = "3000"
    FINANCE_PORTAL_URL    = "http://finance-portal-backend:3002"
    HEALTH_PORTAL_URL     = "http://powerlifting-app-backend:3005"
    DIARY_PORTAL_URL      = "http://diary-portal-backend:3003"
    PROPOSALS_PORTAL_URL  = "http://proposals-portal-backend:3004"
    DIRECTIVES_PORTAL_URL = "http://directives-portal-backend:3006"
    FRONTEND_URL          = "http://main-portal-frontend:3001"
  }
}

resource "kubernetes_config_map" "finance_portal_config" {
  metadata {
    name      = "finance-portal-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    AWS_REGION     = var.region
    DYNAMODB_TABLE = var.dynamodb_finance_table
    NODE_ENV       = "production"
    PORT           = "3002"
    FRONTEND_URL   = "http://finance-portal-frontend:3001"
  }
}

resource "kubernetes_config_map" "diary_portal_config" {
  metadata {
    name      = "diary-portal-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    AWS_REGION     = var.region
    DYNAMODB_TABLE = var.dynamodb_diary_entries_table
    NODE_ENV       = "production"
    PORT           = "3003"
    FRONTEND_URL   = "http://diary-portal-frontend:3001"
  }
}

resource "kubernetes_config_map" "proposals_portal_config" {
  metadata {
    name      = "proposals-portal-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    AWS_REGION     = var.region
    DYNAMODB_TABLE = var.dynamodb_proposals_table
    NODE_ENV       = "production"
    PORT           = "3004"
    FRONTEND_URL   = "http://proposals-portal-frontend:3001"
  }
}

resource "kubernetes_config_map" "powerlifting_app_config" {
  metadata {
    name      = "powerlifting-app-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    AWS_REGION                = var.region
    DYNAMODB_TABLE            = var.dynamodb_powerlifting_table
    IF_USER_TABLE             = var.dynamodb_user_table
    IF_SESSIONS_TABLE_NAME    = var.dynamodb_sessions_table
    ANALYSIS_CACHE_TABLE_NAME = var.dynamodb_analysis_cache_table
    NODE_ENV                  = "production"
    PORT                      = "3005"
    FRONTEND_URL              = "https://${local.app_domains["powerlifting-app"].domain}"
    DISCORD_CLIENT_ID         = var.discord_client_id
    DISCORD_CLIENT_SECRET     = var.discord_client_secret
    DISCORD_REDIRECT_URI      = var.discord_redirect_uri
    JWT_SECRET                = var.jwt_secret
    COOKIE_DOMAIN             = var.cookie_domain
    COOKIE_SECURE             = var.cookie_secure
  }
}

resource "kubernetes_config_map" "directives_portal_config" {
  metadata {
    name      = "directives-portal-config"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    AWS_REGION           = var.region
    NODE_ENV             = "production"
    PORT                 = "3006"
    IF_AGENT_API_URL     = "http://if-agent-api:8000"
    FRONTEND_URL         = "https://${local.app_domains["directives-portal"].domain}"
    DISCORD_CLIENT_ID    = var.directives_discord_client_id != "" ? var.directives_discord_client_id : var.discord_client_id
    DISCORD_REDIRECT_URI = var.directives_discord_redirect_uri != "" ? var.directives_discord_redirect_uri : "https://${local.app_domains["directives-portal"].domain}/api/auth/discord/callback"
    COOKIE_DOMAIN        = var.directives_cookie_domain
    COOKIE_SECURE        = var.cookie_secure
  }
}

resource "kubernetes_secret" "directives_portal_secrets" {
  metadata {
    name      = "directives-portal-secrets"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    DISCORD_CLIENT_SECRET = var.directives_discord_client_secret != "" ? var.directives_discord_client_secret : var.discord_client_secret
    JWT_SECRET            = var.jwt_secret
  }
}

resource "kubernetes_secret" "tinyauth_secrets" {
  metadata {
    name      = "tinyauth-secrets"
    namespace = kubernetes_namespace.if_portals.metadata[0].name
  }

  data = {
    TINYAUTH_SECRET                              = var.tinyauth_secret
    TINYAUTH_OAUTH_PROVIDERS_GOOGLE_CLIENTID     = var.google_oauth_client_id
    TINYAUTH_OAUTH_PROVIDERS_GOOGLE_CLIENTSECRET = var.google_oauth_client_secret
  }

  type = "Opaque"
}
