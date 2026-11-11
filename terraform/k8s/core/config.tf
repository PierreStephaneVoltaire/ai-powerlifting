data "aws_ssm_parameter" "media_base_url" {
  name = "/powerlifting/media/cloudfront-base-url"
}

data "aws_ssm_parameter" "media_signing_key_pair_id" {
  name = "/powerlifting/media/cloudfront-signing-key-pair-id"
}

resource "kubernetes_config_map_v1" "app" {
  metadata {
    name      = "powerlifting-app-config"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }

  data = {
    AWS_REGION                             = var.region
    DYNAMODB_TABLE                         = var.tables.powerlifting
    IF_USER_TABLE                          = var.tables.users
    IF_SESSIONS_TABLE_NAME                 = var.tables.sessions
    ANALYSIS_CACHE_TABLE_NAME              = var.tables.analysis_cache
    POWERLIFTING_MASTER_COMPETITIONS_TABLE = var.tables.master_competitions
    POWERLIFTING_USER_COMPETITIONS_TABLE   = var.tables.user_competitions
    POWERLIFTING_MASTER_FEDERATIONS_TABLE  = var.tables.master_federations
    POWERLIFTING_USER_FEDERATIONS_TABLE    = var.tables.user_federations
    POWERLIFTING_GOALS_TABLE               = var.tables.goals
    POWERLIFTING_BUDGET_TABLE              = var.tables.budget
    BUDGET_MEDIA_BUCKET                    = var.budget_media_bucket
    NODE_ENV                               = "production"
    PORT                                   = "3005"
    FRONTEND_URL                           = "https://${var.app_domain}"
    DISCORD_CLIENT_ID                      = var.discord_client_id
    DISCORD_REDIRECT_URI                   = "https://${var.app_domain}/api/auth/discord/callback"
    AUTHENTIK_CLIENT_ID                    = var.authentik_client_id
    AUTHENTIK_ISSUER_URL                   = "https://${var.auth_domain}/application/o/${var.authentik_client_id}/"
    AUTHENTIK_JWKS_URL                     = "http://authentik-server.${var.auth_namespace}.svc.cluster.local/application/o/${var.authentik_client_id}/jwks/"
    AUTHENTIK_REDIRECT_URI                 = "https://${var.app_domain}/api/auth/authentik/callback"
    COOKIE_DOMAIN                          = var.cookie_domain
    COOKIE_SECURE                          = "true"
    MEDIA_CDN_BASE_URL                     = nonsensitive(data.aws_ssm_parameter.media_base_url.value)
    MEDIA_SIGNING_KEY_PAIR_ID              = nonsensitive(data.aws_ssm_parameter.media_signing_key_pair_id.value)
    MEDIA_VIDEO_URL_TTL_HOURS              = "72"
    VALKEY_URL                             = "redis://pl-valkey.${var.namespace}.svc.cluster.local:6379"
    IF_API_URL                             = "http://pl-coach.${var.namespace}.svc.cluster.local:8000"
    AWS_SHARED_CREDENTIALS_FILE            = "/secrets/aws/credentials"
    AWS_CONFIG_FILE                        = "/secrets/aws/config"
  }
}
