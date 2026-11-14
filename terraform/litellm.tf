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

resource "aws_ssm_parameter" "litellm_master_key" {
  name  = "/powerlifting/litellm/master_key"
  type  = "SecureString"
  value = "sk-${random_password.litellm_master_key.result}"
}

resource "aws_ssm_parameter" "litellm_provider_key" {
  for_each = nonsensitive(toset(keys(var.litellm_provider_keys)))

  name  = "/powerlifting/litellm/provider_keys/${each.key}"
  type  = "SecureString"
  value = var.litellm_provider_keys[each.key]
}
