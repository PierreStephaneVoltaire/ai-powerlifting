terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws        = { source = "hashicorp/aws" }
    tls        = { source = "hashicorp/tls" }
    archive    = { source = "hashicorp/archive" }
    kubernetes = { source = "hashicorp/kubernetes" }
    helm       = { source = "hashicorp/helm" }
    kubectl    = { source = "gavinbunney/kubectl" }
    cloudflare = { source = "cloudflare/cloudflare", version = "~> 4.52" }
    random     = { source = "hashicorp/random" }
  }
}
