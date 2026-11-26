data "aws_ssm_parameter" "media_signing_private_key" {
  name            = "/powerlifting/media/cloudfront-signing-private-key"
  with_decryption = true
}

resource "kubernetes_secret_v1" "backend" {
  metadata {
    name      = "powerlifting-app-backend-secrets"
    namespace = var.namespace
  }

  data = { MEDIA_SIGNING_PRIVATE_KEY = data.aws_ssm_parameter.media_signing_private_key.value }
}
