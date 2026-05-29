locals {
  # Load every utils/*/domain.yaml relative to the terraform/ directory.
  # Produces: { "powerlifting-app" => { domain, zone, google_auth? }, ... }
  app_domains = {
    for f in fileset(path.module, "../utils/*/domain.yaml") :
    regex("utils/([^/]+)/domain\\.yaml", f)[0] => yamldecode(file("${path.module}/${f}"))
  }

  # Apps that have a domain field → get a tunnel ingress rule + DNS record + HTTPRoute.
  public_apps = {
    for app, cfg in local.app_domains : app => cfg
    if can(cfg.domain)
  }

  # Subset of public_apps where google_auth is explicitly true → get Cloudflare Access resources.
  protected_apps = {
    for app, cfg in local.public_apps : app => cfg
    if try(cfg.google_auth, false) == true
  }

  # Unique apex zones across all public apps — used for cloudflare_zone.managed and namecheap_domain_records.
  unique_zones = toset([for app, cfg in local.public_apps : cfg.zone])

  # Backend ports matching the for_each in k8s-deployments.tf.
  portal_backend_ports = {
    "main-portal"       = 3000
    "finance-portal"    = 3002
    "diary-portal"      = 3003
    "proposals-portal"  = 3004
    "powerlifting-app"  = 3005
    "directives-portal" = 3006
  }
}
