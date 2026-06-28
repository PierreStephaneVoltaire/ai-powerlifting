resource "aws_ssm_parameter" "pl_openrouter_key" {
  name  = "/powerlifting-app/openrouter-api-key"
  type  = "String"
  value = var.openrouter_api_key
}

resource "aws_ssm_parameter" "pl_internal_token" {
  name  = "/powerlifting-app/internal-token"
  type  = "String"
  value = var.pl_internal_token
}

data "aws_ssm_parameter" "openrouter_key" {
  name = "/powerlifting-app/openrouter-api-key"
}

data "aws_ssm_parameter" "internal_token" {
  name = "/powerlifting-app/internal-token"
}
