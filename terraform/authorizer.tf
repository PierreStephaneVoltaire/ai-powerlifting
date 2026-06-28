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

resource "aws_apigatewayv2_integration" "pl_authorizer" {
  api_id = aws_apigatewayv2_api.health_api.id

  integration_type   = "AWS_PROXY"
  integration_method = "POST"
  integration_uri    = aws_lambda_function.pl_authorizer.invoke_arn
}

resource "aws_apigatewayv2_authorizer" "pl_internal" {
  name                              = "internal-token"
  api_id                            = aws_apigatewayv2_api.health_api.id
  authorizer_type                   = "REQUEST"
  identity_sources                  = ["$request.header.X-Internal-Token"]
  enable_simple_responses           = true
  authorizer_payload_format_version = "2.0"
  authorizer_uri                    = aws_lambda_function.pl_authorizer.invoke_arn
}

resource "aws_lambda_permission" "pl_authorizer_invoke" {
  statement_id  = "AllowAPIGatewayInvokeAuthorizer"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.pl_authorizer.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.health_api.execution_arn}/*/*"
}
