variable "function_name" {
  type = string
}

variable "table_name" {
  type = string
}

variable "table_arn" {
  type = string
}

variable "stream_arn" {
  type = string
}

variable "zip_path" {
  type = string
}

variable "log_retention_days" {
  type    = number
  default = 30
}
