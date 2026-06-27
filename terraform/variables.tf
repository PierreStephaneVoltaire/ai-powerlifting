variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "ecr_repository_prefix" {
  type    = string
  default = "if"
}

# DynamoDB table names — created by the main infra stack, referenced here
# for the video thumbnail Lambda's IAM policy and env vars.
variable "dynamodb_health_table" {
  type    = string
  default = "if-health"
}

variable "dynamodb_sessions_table" {
  type    = string
  default = "if-sessions"
}

# DynamoDB table names consumed by the Phase 3 health lambdas.
# Created by the main infra stack; referenced here for IAM + env vars.
variable "dynamodb_templates_table" {
  type    = string
  default = "if-health-templates"
}

variable "dynamodb_analysis_cache_table" {
  type    = string
  default = "if-powerlifting-analysis-cache"
}

variable "dynamodb_proposals_table" {
  type    = string
  default = "if-proposals"
}

# S3 bucket holding the OpenPowerlifting CSV dataset read by the stats lambdas
# (Stream B). The portal backend warm-starts /tmp/sandbox from this bucket.
variable "powerlifting_s3_bucket" {
  type    = string
  default = "powerlifting-openpowerlifting-dataset"
}

# Shared function name prefix for the Phase 3 health lambdas. Each tool's
# function_name is "${var.lambda_function_prefix}${tool_name}" (tool names use
# hyphens, e.g. pl-kg_to_lb). Matches the POWERLIFTING_LAMBDA_PREFIX=pl- env
# the backend uses in Phase 2.
variable "lambda_function_prefix" {
  type    = string
  default = "pl-"
}

# Lambda runtime/handler shared by all Phase 3 health lambdas.
variable "lambda_runtime" {
  type    = string
  default = "python3.12"
}

variable "lambda_handler" {
  type    = string
  default = "handler.handler"
}

# Optional provisioned concurrency for the stats lambdas (Stream B). 0 = off.
variable "stats_provisioned_concurrency" {
  type    = number
  default = 0
}
