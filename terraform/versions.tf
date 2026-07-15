terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws        = { source = "hashicorp/aws" }
    archive    = { source = "hashicorp/archive" }
    kubernetes = { source = "hashicorp/kubernetes" }
    helm       = { source = "hashicorp/helm" }
    kubectl    = { source = "gavinbunney/kubectl" }
  }
}
