resource "cloudflare_zone" "this" {
  account_id = var.account_id
  zone       = var.zone
  plan       = var.zone_plan
}

resource "random_id" "secret" {
  byte_length = 35
}

resource "cloudflare_zero_trust_tunnel_cloudflared" "this" {
  account_id = var.account_id
  name       = var.name
  secret     = random_id.secret.b64_std
}

resource "cloudflare_zero_trust_tunnel_cloudflared_config" "this" {
  account_id = var.account_id
  tunnel_id  = cloudflare_zero_trust_tunnel_cloudflared.this.id

  config {
    ingress_rule {
      hostname = var.hostname
      service  = var.origin_url
      origin_request {
        http_host_header = var.hostname
      }
    }

    ingress_rule {
      hostname = var.auth_hostname
      service  = var.auth_origin_url
      origin_request {
        http_host_header = var.auth_hostname
      }
    }

    ingress_rule {
      hostname = var.llm_hostname
      service  = var.llm_origin_url
      origin_request {
        http_host_header = var.llm_hostname
      }
    }

    ingress_rule {
      service = "http_status:404"
    }
  }
}

resource "cloudflare_record" "app" {
  zone_id = cloudflare_zone.this.id
  name    = var.hostname
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
}

resource "cloudflare_record" "auth" {
  zone_id = cloudflare_zone.this.id
  name    = trimsuffix(var.auth_hostname, ".${var.zone}")
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
}

resource "cloudflare_record" "llm" {
  zone_id = cloudflare_zone.this.id
  name    = trimsuffix(var.llm_hostname, ".${var.zone}")
  type    = "CNAME"
  content = "${cloudflare_zero_trust_tunnel_cloudflared.this.id}.cfargotunnel.com"
  proxied = true
}

resource "aws_ssm_parameter" "token" {
  name  = var.token_parameter_name
  type  = "SecureString"
  value = cloudflare_zero_trust_tunnel_cloudflared.this.tunnel_token
}
