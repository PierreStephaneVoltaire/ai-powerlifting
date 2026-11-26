locals {
  isolation = {
    app     = { ingress = var.app_inputs.ingress, egress = var.app_inputs.egress }
    coach   = { ingress = var.coach_inputs.ingress, egress = var.coach_inputs.egress }
    network = { ingress = [], egress = [] }
  }
  api_egress = [for cidr in var.kubernetes_api_cidrs : {
    to    = [{ ipBlock = { cidr = cidr } }]
    ports = [{ protocol = "TCP", port = 443 }, { protocol = "TCP", port = 6443 }]
  }]
  policy_patches = { for app, policies in local.policy_docs : app => [
    for d in policies : {
      target = { kind = d.kind, name = d.metadata.name }
      patch = contains(setunion(local.isolation[app].ingress, local.isolation[app].egress), d.spec.podSelector.matchLabels.app) ? yamlencode([
        {
          op   = "replace"
          path = "/spec"
          value = merge({ podSelector = d.spec.podSelector, policyTypes = concat(
            contains(local.isolation[app].ingress, d.spec.podSelector.matchLabels.app) ? ["Ingress"] : [],
            contains(local.isolation[app].egress, d.spec.podSelector.matchLabels.app) ? ["Egress"] : []
            ) },
            contains(local.isolation[app].ingress, d.spec.podSelector.matchLabels.app) ? { ingress = d.spec.ingress } : {},
            contains(local.isolation[app].egress, d.spec.podSelector.matchLabels.app) ? { egress = concat(
              [for rule in d.spec.egress : rule if app != "app" || !can(rule.to[0].podSelector.matchLabels["gateway.networking.k8s.io/gateway-name"]) || contains(var.app_inputs.waypoint_callers, d.spec.podSelector.matchLabels.app)],
              contains(["pl-assistant", "ecr-token-refresher"], d.spec.podSelector.matchLabels.app) ? local.api_egress : []
          ) } : {})
        }
      ]) : yamlencode({ apiVersion = d.apiVersion, kind = d.kind, metadata = { name = d.metadata.name }, "$patch" = "delete" })
    }
  ] }
}

variable "waypoint_network_policy_enabled" {
  type    = bool
  default = false
}

locals {
  waypoint_patches = { for app, docs in local.docs : app => [
    for d in docs : {
      target = { kind = d.kind, name = d.metadata.name }
      patch = var.waypoint_network_policy_enabled ? yamlencode([{
        op    = "replace", path = "/spec/ingress/0/from",
        value = [for caller in var.app_inputs.waypoint_callers : { podSelector = { matchLabels = { app = caller } } }]
      }]) : yamlencode({ apiVersion = d.apiVersion, kind = d.kind, metadata = { name = d.metadata.name }, "$patch" = "delete" })
    } if try(d.metadata.annotations["nolift.io/waypoint-isolation"] == "true", false)
  ] }
}
