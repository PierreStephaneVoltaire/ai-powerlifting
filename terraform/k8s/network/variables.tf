variable "namespace" {
  type = string
}

variable "app_domain" {
  type = string
}

variable "auth_domain" {
  type = string
}

variable "auth_namespace" {
  type    = string
  default = "if-portals"
}

