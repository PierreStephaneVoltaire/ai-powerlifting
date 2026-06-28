data "archive_file" "pl_authorizer" {
  type        = "zip"
  output_path = "${path.module}/build/pl_authorizer_auth.zip"
  source_dir  = "${path.module}/../lambda/pl_authorizer"
}

resource "aws_lambda_function" "pl_authorizer" {
  function_name = "${var.lambda_function_prefix}authorizer"
  role          = aws_iam_role.lambda_exec.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 128
  timeout       = 5

  filename         = data.archive_file.pl_authorizer.output_path
  source_code_hash = data.archive_file.pl_authorizer.output_base64sha256

  environment {
    variables = {
      INTERNAL_API_TOKEN = data.aws_ssm_parameter.internal_token.value
    }
  }

  tags = {
    Project = "powerlifting-app"
    Service = "pl-authorizer"
  }
}