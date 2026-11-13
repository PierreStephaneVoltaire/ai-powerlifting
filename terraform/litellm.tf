variable "llm_domain" {
  type = string
}

variable "litellm_provider_keys" {
  type      = map(string)
  sensitive = true
}

resource "random_password" "litellm_master_key" {
  length  = 48
  special = false
}

resource "aws_secretsmanager_secret" "litellm" {
  name = "powerlifting/litellm"
}

resource "aws_secretsmanager_secret_version" "litellm" {
  secret_id = aws_secretsmanager_secret.litellm.id
  secret_string = jsonencode({
    master_key    = "sk-${random_password.litellm_master_key.result}"
    provider_keys = var.litellm_provider_keys
  })
}
