output "backend_repository_url" {
  value = aws_ecr_repository.powerlifting_backend.repository_url
}

output "frontend_repository_url" {
  value = aws_ecr_repository.powerlifting_frontend.repository_url
}

output "cloudfront_media_domain" {
  description = "CloudFront domain serving the powerlifting session videos bucket"
  value       = aws_cloudfront_distribution.session_videos.domain_name
}

output "cloudfront_media_base_url" {
  description = "Full https URL for CloudFront media distribution (used as VITE_CLOUDFRONT_MEDIA_BASE_URL)"
  value       = "https://${aws_cloudfront_distribution.session_videos.domain_name}"
}


output "lambda_exec_role_arn" {
  description = "ARN of the shared Lambda execution role for all health lambdas"
  value       = aws_iam_role.lambda_exec.arn
}

output "lambda_function_names" {
  description = "Map of tool name -> deployed Lambda function name (pl-<tool>)"
  value = {
    for name, fn in aws_lambda_function.health_tool : name => fn.function_name
  }
}

output "lambda_function_arns" {
  description = "Map of tool name -> deployed Lambda function ARN"
  value = {
    for name, fn in aws_lambda_function.health_tool : name => fn.arn
  }
}

output "lambda_layer_arns" {
  description = "Map of layer key -> Lambda layer version ARN"
  value       = local.layer_arns
}


output "api_gateway_id" {
  description = "ID of the powerlifting health HTTP API (aws_apigatewayv2_api.health_api)"
  value       = aws_apigatewayv2_api.health_api.id
}

output "api_gateway_endpoint_base_url" {
  description = "API Gateway HTTP API base URL; append /{tool} to invoke a specific health lambda (e.g. .../{tool}/kg_to_lb)"
  value       = "${aws_apigatewayv2_api.health_api.api_endpoint}/{tool}"
}
output "lambda_openapi_url" {
  value = "${aws_apigatewayv2_api.health_api.api_endpoint}/openapi.json"
}



