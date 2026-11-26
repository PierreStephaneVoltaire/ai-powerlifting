output "manifest_inputs" {
  sensitive = true
  value = {
    job_token_public_key = local.job_token_public_key
    mcp_aliases          = join(",", sort(keys(local.litellm_mcp_registry)))
    litellm_checksum     = sha256(kubernetes_config_map_v1.litellm.data["config.yaml"])
    reference_checksum   = sha256(kubernetes_config_map_v1.reference_litellm.data["config.yaml"])
    waypoint_callers     = [for caller in local.network_waypoint_callers : lookup(local.network_pod_names, caller, caller)]
    ingress              = var.network_policy_ingress_workloads
    egress               = var.network_policy_egress_workloads
  }

  precondition {
    condition     = !var.waypoint_network_policy_enabled || var.external_service_entries_enabled
    error_message = "Stage external ServiceEntries before isolating the waypoint."
  }
  precondition {
    condition     = length(setsubtract(setunion(var.network_policy_ingress_workloads, var.network_policy_egress_workloads), local.network_valid_workloads)) == 0
    error_message = "Unknown app network policy selector."
  }
  precondition {
    condition     = length(var.network_policy_egress_workloads) == 0 || var.external_service_entries_enabled
    error_message = "Enable external ServiceEntries before isolating egress."
  }
  precondition {
    condition     = length(setintersection(var.network_policy_egress_workloads, ["ecr-token-refresher", "pl-assistant"])) == 0 || length(var.kubernetes_api_cidrs) > 0
    error_message = "Set kubernetes_api_cidrs before isolating API clients."
  }
}
