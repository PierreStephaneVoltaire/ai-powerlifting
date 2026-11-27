import {
  to = tailscale_acl.policy
  id = "acl"
}

data "tailscale_acl" "current" {}
locals {
  policy       = jsondecode(data.tailscale_acl.current.json)
  worker_grant = { src = ["tag:k3s-server", "tag:k3s-worker"], dst = ["tag:k3s-server", "tag:k3s-worker"], ip = ["*"] }
}
resource "tailscale_acl" "policy" {
  acl = jsonencode(merge(local.policy, {
    tagOwners = merge({ "tag:k3s-server" = ["autogroup:admin"], "tag:k3s-worker" = ["autogroup:admin"] }, try(local.policy.tagOwners, {}))
    grants    = concat([for grant in try(local.policy.grants, []) : grant if jsonencode(grant) != jsonencode(local.worker_grant)], [local.worker_grant])
  }))
  lifecycle {
    prevent_destroy = true
    precondition {
      condition = alltrue(concat(
        [for rule in try(local.policy.acls, []) : length(setintersection(toset(try(rule.src, [])), toset(["*", "autogroup:tagged", "tag:k3s-worker"]))) == 0 || alltrue([for dst in try(rule.dst, []) : startswith(dst, "tag:k3s-server:") || startswith(dst, "tag:k3s-worker:")])],
        [for rule in try(local.policy.grants, []) : length(setintersection(toset(try(rule.src, [])), toset(["*", "autogroup:tagged", "tag:k3s-worker"]))) == 0 || alltrue([for dst in try(rule.dst, []) : contains(["tag:k3s-server", "tag:k3s-worker"], dst)])]
      ))
      error_message = "The existing tailnet policy allows wildcard sources to reach other devices; restrict those rules before joining workers."
    }
  }
}
resource "tailscale_dns_preferences" "tailnet" { magic_dns = true }
resource "tailscale_oauth_client" "worker_join" {
  scopes     = ["auth_keys"]
  tags       = ["tag:k3s-worker"]
  depends_on = [tailscale_acl.policy]
}
resource "tailscale_oauth_client" "server_join" {
  scopes     = ["auth_keys"]
  tags       = ["tag:k3s-server"]
  depends_on = [tailscale_acl.policy]
}
resource "aws_ssm_parameter" "tailscale_key" {
  lifecycle { prevent_destroy = true }
  name  = "/nolift/k3s/tailscale-worker-key"
  type  = "SecureString"
  value = "${tailscale_oauth_client.worker_join.key}?ephemeral=false&preauthorized=true"
}

resource "tailscale_oauth_client" "reaper" {
  scopes     = ["devices:core"]
  tags       = ["tag:k3s-worker"]
  depends_on = [tailscale_acl.policy]
}
resource "kubernetes_secret_v1" "reaper" {
  metadata {
    name      = "node-reaper-tailscale"
    namespace = "kube-system"
  }
  data = { client_id = tailscale_oauth_client.reaper.id, client_secret = tailscale_oauth_client.reaper.key }
}
