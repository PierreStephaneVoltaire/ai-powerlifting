resource "tls_private_key" "media_signing" {
  algorithm = "RSA"
  rsa_bits  = 2048
}

resource "aws_cloudfront_public_key" "media" {
  name        = "${var.distribution_name}-media"
  encoded_key = tls_private_key.media_signing.public_key_pem
}

resource "aws_cloudfront_key_group" "media" {
  name  = "${var.distribution_name}-media"
  items = [aws_cloudfront_public_key.media.id]
}

resource "aws_ssm_parameter" "media_signing_private_key" {
  name  = "/powerlifting/media/cloudfront-signing-private-key"
  type  = "SecureString"
  value = tls_private_key.media_signing.private_key_pem
}

resource "aws_ssm_parameter" "media_signing_key_pair_id" {
  name  = "/powerlifting/media/cloudfront-signing-key-pair-id"
  type  = "String"
  value = aws_cloudfront_public_key.media.id
}

resource "aws_ssm_parameter" "media_base_url" {
  name  = "/powerlifting/media/cloudfront-base-url"
  type  = "String"
  value = "https://${aws_cloudfront_distribution.this.domain_name}"
}
