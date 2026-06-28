
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

  integration_method = "POST"
  integration_uri    = aws_lambda_function.health_tool[each.key].invoke_arn
}

resource "aws_apigatewayv2_route" "tool" {
  for_each = local.lambda_function_configs

  api_id             = aws_apigatewayv2_api.health_api.id
  route_key          = "ANY /${each.key}"
  target             = "integrations/${aws_apigatewayv2_integration.tool[each.key].id}"
  authorizer_id      = aws_apigatewayv2_authorizer.pl_internal.id
  authorization_type = "CUSTOM"
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

resource "aws_lambda_permission" "apigw" {
  for_each = local.lambda_function_configs

  statement_id  = "AllowAPIGatewayInvoke-${each.key}"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health_tool[each.key].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.health_api.execution_arn}/*/*"
}

resource "aws_apigatewayv2_integration" "openapi" {
  api_id = aws_apigatewayv2_api.health_api.id

  integration_type = "AWS_PROXY"

  integration_method = "POST"
  integration_uri    = aws_lambda_function.health_tool["tool_registry"].invoke_arn
}

resource "aws_apigatewayv2_route" "openapi" {
  api_id = aws_apigatewayv2_api.health_api.id

  route_key = "GET /openapi.json"
  target    = "integrations/${aws_apigatewayv2_integration.openapi.id}"
}

resource "aws_lambda_permission" "openapi" {
  statement_id  = "AllowAPIGatewayInvoke-openapi"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.health_tool["tool_registry"].function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.health_api.execution_arn}/*/*"
}
