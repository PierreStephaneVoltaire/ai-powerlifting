data "aws_ssm_parameter" "media_signing_private_key" {
  name            = "/powerlifting/media/cloudfront-signing-private-key"
  with_decryption = true
}

resource "random_password" "principal" {
  length  = 64
  special = false
}

resource "random_password" "session" {
  length  = 64
  special = false
}

resource "kubernetes_secret_v1" "app" {
  metadata {
    name      = "powerlifting-app-secrets"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }

  data = {
    INTERNAL_API_TOKEN        = var.internal_api_token
    PL_PRINCIPAL_SECRET       = random_password.principal.result
    SESSION_SECRET            = random_password.session.result
    JWT_SECRET                = var.jwt_secret
    DISCORD_CLIENT_SECRET     = var.discord_client_secret
    AUTHENTIK_CLIENT_SECRET   = var.authentik_client_secret
    MEDIA_SIGNING_PRIVATE_KEY = data.aws_ssm_parameter.media_signing_private_key.value
  }
}

data "aws_ssm_parameter" "pod_credentials" {
  name            = "/powerlifting/k8s/aws-credentials"
  with_decryption = true
}

locals {
  pod_credentials = jsondecode(data.aws_ssm_parameter.pod_credentials.value)
}

resource "kubernetes_secret_v1" "aws_credentials" {
  metadata {
    name      = "pl-aws-credentials"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }

  data = {
    credentials = "[default]\naws_access_key_id = ${local.pod_credentials.aws_access_key_id}\naws_secret_access_key = ${local.pod_credentials.aws_secret_access_key}\n"
    config      = "[default]\nregion = ${var.region}\n"
  }
}

data "aws_ssm_parameter" "tunnel_token" {
  name            = "/powerlifting/k8s/tunnel-token"
  with_decryption = true
}

resource "kubernetes_secret_v1" "tunnel" {
  metadata {
    name      = "cloudflared-token"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }

  data = {
    token = data.aws_ssm_parameter.tunnel_token.value
  }
}
