variable "repository_prefix" {
  type        = string
  description = "Prefix for ECR repository names (e.g. \"if\")."
}

variable "repository_names" {
  type        = list(string)
  description = "Suffix names to create repositories for (e.g. [\"powerlifting-app-backend\"])."
}
