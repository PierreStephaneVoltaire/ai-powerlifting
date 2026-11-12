terraform {
  required_version = ">= 1.5.0"

  required_providers {
    aws        = { source = "hashicorp/aws" }
    kubectl    = { source = "alekc/kubectl", version = "~> 2.1" }
    kubernetes = { source = "hashicorp/kubernetes" }
  }
}
