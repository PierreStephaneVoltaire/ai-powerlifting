variable "region" {
  type    = string
  default = "ca-central-1"
}

variable "ci_role_name" {
  description = "IAM role the GitHub Actions pipeline assumes"
  type        = string
  default     = "github-actions"
}
