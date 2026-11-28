import {
  to = tailscale_acl.policy
  id = "acl"
}

data "tailscale_acl" "current" {}
locals {
  policy       = jsondecode(data.tailscale_acl.current.json)
  worker_grant = { src = ["tag:k3s-server", "tag:k3s-worker"], dst = ["tag:k3s-server", "tag:k3s-worker"], ip = ["*"] }
  k3s_tag_owners = {
    for tag in local.worker_grant.src : tag => distinct(concat(try(local.policy.tagOwners[tag], ["autogroup:admin"]), [tag]))
  }
}
resource "tailscale_acl" "policy" {
  acl = jsonencode(merge(local.policy, {
    tagOwners = merge(try(local.policy.tagOwners, {}), local.k3s_tag_owners)
    grants    = concat([for grant in try(local.policy.grants, []) : grant if jsonencode(grant) != jsonencode(local.worker_grant)], [local.worker_grant])
  }))
  lifecycle { prevent_destroy = true }
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
