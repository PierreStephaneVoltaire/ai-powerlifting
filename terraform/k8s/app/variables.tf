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
    services         = string
    analytics        = string
    rankings         = string
    analytics_ai     = string
    prompt_cache_api = string
    analytics_export = string
    glossary         = string
    sessions         = optional(string, "if-powerlifting-sessions")
    program          = optional(string, "if-powerlifting-program")
    performance      = optional(string, "if-powerlifting-performance")
    federation       = optional(string, "if-powerlifting-federation")
    goals            = optional(string, "if-powerlifting-goals")
    lift_profiles    = optional(string, "if-powerlifting-lift-profiles")
    export           = optional(string, "if-powerlifting-export")
    imports          = optional(string, "if-powerlifting-imports")
    templates        = optional(string, "if-powerlifting-templates")
    weight_log       = optional(string, "if-powerlifting-weight-log")
    calculations     = optional(string, "if-powerlifting-calculations")
    competition      = optional(string, "if-powerlifting-competition")
    profile          = optional(string, "if-powerlifting-profile")
    assistant        = optional(string, "if-powerlifting-assistant")
    backend          = string
    frontend         = string
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
