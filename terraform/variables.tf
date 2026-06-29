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

variable "openrouter_api_key" {
  type        = string
  sensitive   = true
  description = "OpenRouter API key for LLM calls. Stored in SSM."
}

variable "pl_internal_token" {
  type        = string
  sensitive   = true
  description = "Internal API token for powerlifting-app service auth. Stored in SSM."
}

variable "kubeconfig_path" {
  type    = string
  default = "~/.kube/config"
}

variable "kubeconfig_context" {
  type    = string
  default = "default"
}

variable "fission_powerlifting_env_enabled" {
  type    = bool
  default = true
}

variable "fission_powerlifting_env_name" {
  type    = string
  default = "pl-fission-tools"
}

variable "fission_powerlifting_env_namespace" {
  type    = string
  default = "fission"
}

variable "fission_powerlifting_env_runtime_image" {
  type    = string
  default = "fission/python-env:1.20.4"
}

variable "fission_powerlifting_function_namespace" {
  type    = string
  default = "if-portals"
}

variable "fission_powerlifting_router_dns" {
  type    = string
  default = "router.fission.svc.cluster.local"
}




variable "node_name" {
  type    = string
  default = "sirsimpalot-g5-5000"
}
