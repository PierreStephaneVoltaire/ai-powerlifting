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
