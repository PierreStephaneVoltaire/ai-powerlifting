variable "region" {
  type = string
}

variable "namespace" {
  type = string
}

variable "storage_class" {
  type = string
}

variable "repositories" {
  type = object({
    services  = string
    analytics = string
    backend   = string
    frontend  = string
  })
}

variable "image_tag" {
  type    = string
  default = "latest"

  validation {
    condition     = can(regex("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$", var.image_tag))
    error_message = "image_tag must be a valid Docker or ECR tag."
  }
}

variable "dataset_bucket" {
  type = string
}

variable "app_domain" {
  type = string
}

variable "auth_namespace" {
  type    = string
  default = "if-portals"
}
