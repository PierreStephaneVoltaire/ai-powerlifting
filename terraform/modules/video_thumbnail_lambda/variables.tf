variable "function_name" {
  type        = string
  description = "Lambda function name (e.g. \"video-thumbnail-generator\")."
}

variable "lambda_role_name" {
  type        = string
  description = "Name of the IAM role created for this lambda."
}

variable "region" {
  type        = string
  description = "AWS region (used in dynamodb ARN construction)."
}

variable "videos_bucket_id" {
  type        = string
  description = "Bucket ID (name) of the session videos bucket."
}

variable "videos_bucket_arn" {
  type        = string
  description = "Bucket ARN of the session videos bucket."
}

variable "health_table_name" {
  type        = string
  description = "Name of the health DynamoDB table."
}

variable "sessions_table_name" {
  type        = string
  description = "Name of the sessions DynamoDB table."
}
