variable "network_policy_ingress_workloads" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_ingress_workloads, toset(["pl-coach", "pl-coach-discord"]))) == 0
    error_message = "Only pl-coach and pl-coach-discord are managed here."
  }
}

variable "network_policy_egress_workloads" {
  type    = set(string)
  default = []
  validation {
    condition     = length(setsubtract(var.network_policy_egress_workloads, toset(["pl-coach", "pl-coach-discord"]))) == 0
    error_message = "Only pl-coach and pl-coach-discord are managed here."
  }
}
