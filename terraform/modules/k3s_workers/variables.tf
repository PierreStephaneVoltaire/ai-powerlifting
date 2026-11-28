variable "region" { type = string }
variable "azs" { type = list(string) }
variable "min" { type = number }
variable "desired" { type = number }
variable "max" { type = number }
variable "instance_types" { type = list(string) }
variable "ami_ssm_parameter" { type = string }
variable "root_volume_gib" { type = number }
variable "spot_max_price" {
  type    = string
  default = null
}
variable "home_lan_cidr" { type = string }
