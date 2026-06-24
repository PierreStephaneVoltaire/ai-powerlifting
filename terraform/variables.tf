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
