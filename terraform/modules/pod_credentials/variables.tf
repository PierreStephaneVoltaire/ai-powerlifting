variable "user_name" {
  type = string
}

variable "table_names" {
  type = list(string)
}

variable "bucket_arns" {
  type = list(string)
}

variable "parameter_name" {
  type = string
}

variable "repository_names" {
  type = list(string)
}
