variable "region" {
  type        = string
  description = "AWS region this stack is deployed to."
  default     = "ca-central-1"
}

variable "ecr_repository_prefix" {
  type        = string
  description = "Prefix prepended to ECR repository names (e.g. \"if\" -> \"if-powerlifting-app-backend\")."
  default     = "if"
}

variable "dynamodb_health_table" {
  type        = string
  description = "Name of the health metrics DynamoDB table."
  default     = "if-health"
}

variable "dynamodb_sessions_table" {
  type        = string
  description = "Name of the training sessions DynamoDB table."
  default     = "if-sessions"
}

variable "dynamodb_templates_table" {
  type        = string
  description = "Name of the templates DynamoDB table."
  default     = "if-health-templates"
}

variable "dynamodb_analysis_cache_table" {
  type        = string
  description = "Name of the analysis cache DynamoDB table."
  default     = "if-powerlifting-analysis-cache"
}

variable "dynamodb_proposals_table" {
  type        = string
  description = "Name of the proposals DynamoDB table."
  default     = "if-proposals"
}

variable "powerlifting_s3_bucket" {
  type        = string
  description = "Name of the S3 bucket that holds the openpowerlifting dataset."
  default     = "powerlifting-openpowerlifting-dataset"
}

variable "openrouter_api_key" {
  type        = string
  description = "OpenRouter API key (sourced from SSM plaintext param)."
  default     = ""
  sensitive   = true
}

variable "pl_internal_token" {
  type        = string
  description = "Internal API token for the Fission tools / API Gateway authorizer (sourced from SSM plaintext param)."
  default     = ""
  sensitive   = true
}
