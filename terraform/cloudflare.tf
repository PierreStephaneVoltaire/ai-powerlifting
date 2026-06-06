provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

# ─── Tunnel ───────────────────────────────────────────────────────────────────

resource "random_id" "tunnel_secret" {
  byte_length = 35
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "this" {
  account_id = var.cloudflare_account_id
  name       = var.cloudflare_tunnel_name
  secret     = random_id.tunnel_secret.b64_std
}

# ─── Zones (one per unique apex in domain.yaml files) ────────────────────────
# Creates the zone in Cloudflare. After first apply, update the nameservers at
# Namecheap to the values in the `cloudflare_nameservers` Terraform output.
# If a zone was already created manually, import it:
#   terraform import 'cloudflare_zone.managed["example.com"]' <zone_id>

resource "cloudflare_zone" "managed" {
  for_each   = local.unique_zones
  account_id = var.cloudflare_account_id
  zone       = each.value
  plan       = var.cloudflare_zone_plan
}

# ─── DNS records ──────────────────────────────────────────────────────────────

resource "cloudflare_record" "tunnel_cname" {
  for_each = local.public_apps

  zone_id = cloudflare_zone.managed[each.value.zone].id
  name    = each.value.domain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
  comment = "Managed by Terraform — tunnel for ${each.key}"
}

resource "cloudflare_record" "logs_cname" {
  zone_id = cloudflare_zone.managed[var.monitoring_zone].id
  name    = local.logs_domain
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
  comment = "Managed by Terraform — tunnel for Grafana log viewer"
}


# ─── Tunnel ingress config ────────────────────────────────────────────────────

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "this" {
  account_id = var.cloudflare_account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.this.id

  depends_on = [cloudflare_zone.managed]

  config {
    dynamic "ingress_rule" {
      for_each = local.public_apps
      content {
        hostname = ingress_rule.value.domain
        service  = "http://nginx-gateway-nginx.default.svc.cluster.local:80"
        origin_request {
          http_host_header = ingress_rule.value.domain
        }
      }
    }
    # Monitoring / Grafana log viewer
    ingress_rule {
      hostname = local.logs_domain
      service  = "http://nginx-gateway-nginx.default.svc.cluster.local:80"
      origin_request {
        http_host_header = local.logs_domain
      }
    }
    # Required catch-all — must be last.
    ingress_rule {
      service = "http_status:404"
    }
  }
}

# ─── Google IdP (reuses existing OAuth client from tinyauth) ──────────────────

resource "cloudflare_zero_trust_access_identity_provider" "google" {
  account_id = var.cloudflare_account_id
  name       = "Google"
  type       = "google"

  config {
    client_id     = var.google_oauth_client_id
    client_secret = var.google_oauth_client_secret
  }
}

# ─── Access Applications (one per protected app) ──────────────────────────────

resource "cloudflare_zero_trust_access_application" "app" {
  for_each = local.protected_apps

  account_id           = var.cloudflare_account_id
  name                 = "${each.key} (${each.value.domain})"
  domain               = each.value.domain
  type                 = "self_hosted"
  session_duration     = "24h"
  app_launcher_visible = true
}

# ─── Access Policies (any valid Google account) ───────────────────────────────

resource "cloudflare_zero_trust_access_policy" "allow_google" {
  for_each = local.protected_apps

  account_id     = var.cloudflare_account_id
  application_id = cloudflare_zero_trust_access_application.app[each.key].id
  name           = "Allow ${each.key}"
  precedence     = 1
  decision       = "allow"

  include {
    login_method = [cloudflare_zero_trust_access_identity_provider.google.id]
  }
}
