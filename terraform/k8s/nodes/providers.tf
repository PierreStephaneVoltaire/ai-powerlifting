terraform {
  backend "s3" {}
  required_version = ">= 1.15.0"
  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
    http       = { source = "hashicorp/http", version = "~> 3.4" }
    random     = { source = "hashicorp/random", version = "~> 3.7" }
    tailscale  = { source = "tailscale/tailscale", version = "~> 0.30.0" }
  }
}
provider "aws" { region = var.region }
provider "kubernetes" {}
provider "tailscale" {}
