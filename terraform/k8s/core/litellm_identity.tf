variable "llm_domain" {
  type = string
}

variable "litellm_sso_users" {
  type = list(string)
}

resource "authentik_provider_oauth2" "litellm" {
  name               = "nolift-litellm"
  client_id          = "nolift-litellm"
  client_type        = "confidential"
  authorization_flow = data.authentik_flow.default_authorization.id
  invalidation_flow  = data.authentik_flow.default_invalidation.id
  signing_key        = data.authentik_certificate_key_pair.default.id
  grant_types        = ["authorization_code", "refresh_token"]
  property_mappings = [
    data.authentik_property_mapping_provider_scope.openid.id,
    data.authentik_property_mapping_provider_scope.email.id,
    data.authentik_property_mapping_provider_scope.profile.id,
  ]
  allowed_redirect_uris = [
    {
      matching_mode     = "strict"
      url               = "https://${var.llm_domain}/sso/callback"
      redirect_uri_type = "authorization"
    },
  ]
}

resource "authentik_application" "litellm" {
  name               = "NoLift LiteLLM"
  slug               = "litellm"
  protocol_provider  = authentik_provider_oauth2.litellm.id
  meta_launch_url    = "https://${var.llm_domain}/ui"
  meta_description   = "LiteLLM admin UI"
  policy_engine_mode = "any"
}

resource "authentik_policy_expression" "litellm_users" {
  name       = "litellm-allowed-users"
  expression = "return request.user.username in ${jsonencode(var.litellm_sso_users)}"
}

resource "authentik_policy_binding" "litellm_users" {
  target = authentik_application.litellm.uuid
  policy = authentik_policy_expression.litellm_users.id
  order  = 0
}

resource "aws_ssm_parameter" "litellm_sso_client_id" {
  name  = "/powerlifting/litellm/sso_client_id"
  type  = "SecureString"
  value = authentik_provider_oauth2.litellm.client_id
}

resource "aws_ssm_parameter" "litellm_sso_client_secret" {
  name  = "/powerlifting/litellm/sso_client_secret"
  type  = "SecureString"
  value = authentik_provider_oauth2.litellm.client_secret
}
