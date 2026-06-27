# ---------------------------------------------------------------------------
# Phase 3 — API Gateway HTTP API (per-tool /{tool} proxy).
#
# One HTTP API fronts all 76 health lambdas. For each tool (for_each over the
# same lambda_function_configs local used by lambda.tf) we create:
#   - aws_apigatewayv2_integration  (AWS_PROXY -> each lambda's invoke_arn)
#   - aws_apigatewayv2_route        (ANY /<tool> -> that integration)
#   - aws_lambda_permission         (allow apigatewayv2 to invoke each lambda)
# A single default stage ($default, auto_deploy=true) serves them all.
# Base URL: ${aws_apigatewayv2_api.health_api.api_endpoint}/{tool}
# ---------------------------------------------------------------------------

resource "aws_apigatewayv2_api" "health_api" {
  name          = "powerlifting-health-http-api"
  protocol_type = "HTTP"

  tags = {
    Project = "powerlifting-app"
    Service = "health-api"
  }
}

resource "aws_apigatewayv2_integration" "tool" {
  for_each = local.lambda_function_configs

  api_id           = aws_apigatewayv2_api.health_api.id
  integration_type = "AWS_PROXY"

  # HTTP APIs with AWS_PROXY integrations invoke the function synchronously over
  # POST; the route's ANY method is mapped to this POST internally.
  integration_method = "POST"
  integration_uri    = aws_lambda_function.health_tool[each.key].invoke_arn
}

resource "aws_apigatewayv2_route" "tool" {
  for_each = local.lambda_function_configs

  api_id    = aws_apigatewayv2_api.health_api.id
  route_key = "ANY /${each.key}"
  target    = "integrations/${aws_apigatewayv2_integration.tool[each.key].id}"
}

resource "aws_apigatewayv2_stage" "default" {
  api_id      = aws_apigatewayv2_api.health_api.id
  name        = "$default"
  auto_deploy = true

  tags = {
    Project = "powerlifting-app"
    Service = "health-api"
  }
}

# Allow API Gateway (HTTP API) to invoke each health lambda. The source_arn
# grants every method/route on this API.
resource "aws_lambda_permission" "apigw" {
  for_each = local.lambda_function_configs

  statement_id  = "AllowAPIGatewayInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health_tool[each.key].function_name
  principal     = "apigatewayv2.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.health_api.execution_arn}/*/*"
}