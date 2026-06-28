variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "ecr_repository_prefix" {
  type    = string
  default = "if"
}

variable "dynamodb_health_table" {
  type    = string
  default = "if-health"
}

variable "dynamodb_sessions_table" {
  type    = string
  default = "if-sessions"
}

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

variable "powerlifting_s3_bucket" {
  type    = string
  default = "powerlifting-openpowerlifting-dataset"
}

variable "lambda_function_prefix" {
  type    = string
  default = "pl-"
}

variable "lambda_runtime" {
  type    = string
  default = "python3.12"
}

variable "lambda_handler" {
  type    = string
  default = "handler.handler"
}
