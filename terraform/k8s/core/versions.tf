terraform {
  required_version = ">= 1.15.0"

  required_providers {
    authentik  = { source = "goauthentik/authentik", version = "2026.5.0" }
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    helm       = { source = "hashicorp/helm", version = "~> 2.17" }
    kubectl    = { source = "gavinbunney/kubectl", version = "~> 1.19" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
    random     = { source = "hashicorp/random", version = "~> 3.7" }
  }
}
