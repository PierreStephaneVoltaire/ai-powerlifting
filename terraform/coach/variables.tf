variable "region" {
  type = string
}

variable "namespace" {
  description = "Namespace shared with the Powerlifting Services"
  type        = string
}

variable "image_pull_secret" {
  type = string
}

variable "discord_operator_id" {
  description = "Discord user id of the Operator"
  type        = string
  sensitive   = true
}

variable "operator_person" {
  type      = string
  sensitive = true
}

variable "discord_persons" {
  description = "Extra Discord user id to Person mappings"
  type        = map(string)
  sensitive   = true
}
