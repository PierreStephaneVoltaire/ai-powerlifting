variable "llm_domain" {
  type = string
}

variable "litellm_provider_keys" {
  type      = map(string)
  sensitive = true
}

variable "litellm_ui_username" {
  type = string
}

resource "random_password" "litellm_master_key" {
  length  = 48
  special = false
}

resource "random_password" "litellm_ui_password" {
  length  = 32
  special = false
}

resource "aws_ssm_parameter" "litellm_master_key" {
  name  = "/powerlifting/litellm/master_key"
  type  = "SecureString"
  value = "sk-${random_password.litellm_master_key.result}"
}

resource "aws_ssm_parameter" "litellm_ui_username" {
  name  = "/powerlifting/litellm/ui_username"
  type  = "SecureString"
  value = var.litellm_ui_username
}

resource "aws_ssm_parameter" "litellm_ui_password" {
  name  = "/powerlifting/litellm/ui_password"
  type  = "SecureString"
  value = random_password.litellm_ui_password.result
}

resource "aws_ssm_parameter" "litellm_provider_key" {
  for_each = nonsensitive(toset(keys(var.litellm_provider_keys)))

  name  = "/powerlifting/litellm/provider_keys/${each.key}"
  type  = "SecureString"
  value = var.litellm_provider_keys[each.key]
}
