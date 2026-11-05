output "tunnel_id" {
  value = cloudflare_zero_trust_tunnel_cloudflared.this.id
}

output "zone_id" {
  value = cloudflare_zone.this.id
}
