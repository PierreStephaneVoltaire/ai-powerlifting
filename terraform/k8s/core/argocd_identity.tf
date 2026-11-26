variable "argocd_domain" {
  type = string
}

variable "argocd_admins" {
  type = set(string)
}

data "authentik_user" "argocd_admin" {
  for_each = var.argocd_admins
  username = each.key
}

resource "authentik_group" "argocd_admins" {
  name  = "argocd-admins"
  users = [for user in data.authentik_user.argocd_admin : user.id]
}

resource "authentik_provider_oauth2" "argocd" {
  name               = "nolift-argocd"
  client_id          = "nolift-argocd"
  client_type        = "confidential"
  authorization_flow = data.authentik_flow.default_authorization.id
  invalidation_flow  = data.authentik_flow.default_invalidation.id
  signing_key        = data.authentik_certificate_key_pair.default.id
  grant_types        = ["authorization_code", "refresh_token"]
  property_mappings = [
    data.authentik_property_mapping_provider_scope.openid.id,
    data.authentik_property_mapping_provider_scope.profile.id,
    data.authentik_property_mapping_provider_scope.email.id,
    authentik_property_mapping_provider_scope.powerlifting_groups.id,
  ]
  allowed_redirect_uris = [{
    matching_mode     = "strict"
    url               = "https://${var.argocd_domain}/auth/callback"
    redirect_uri_type = "authorization"
  }]
}

resource "authentik_application" "argocd" {
  name              = "NoLift Argo CD"
  slug              = "argocd"
  protocol_provider = authentik_provider_oauth2.argocd.id
  meta_launch_url   = "https://${var.argocd_domain}"
}

resource "authentik_policy_binding" "argocd_admins" {
  target = authentik_application.argocd.uuid
  group  = authentik_group.argocd_admins.id
  order  = 0
}

output "argocd_client_secret" {
  sensitive = true
  value     = authentik_provider_oauth2.argocd.client_secret
}
