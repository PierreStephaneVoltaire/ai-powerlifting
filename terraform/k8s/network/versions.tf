terraform {
  required_version = ">= 1.15.0"

  required_providers {
    helm       = { source = "hashicorp/helm", version = "~> 2.17" }
    http       = { source = "hashicorp/http", version = "~> 3.5" }
    kubectl    = { source = "alekc/kubectl", version = "~> 2.1" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
  }
}
