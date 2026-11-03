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
