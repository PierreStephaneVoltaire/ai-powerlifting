variable "region" {
  type = string
}

variable "namespace" {
  type    = string
  default = "powerlifting"
}

variable "namespace_service_entry_visibility_enabled" {
  type    = bool
  default = false
}
