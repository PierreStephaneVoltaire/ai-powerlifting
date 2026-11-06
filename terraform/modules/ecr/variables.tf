variable "repository_prefix" {
  type = string
}

variable "repository_names" {
  type = list(string)
}

variable "untagged_expiry_repository_names" {
  type = list(string)
}
