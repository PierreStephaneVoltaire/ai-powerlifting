terraform {
  required_version = ">= 1.15.0"

  required_providers {
    aws        = { source = "hashicorp/aws", version = "~> 6.0" }
    kubernetes = { source = "hashicorp/kubernetes", version = "~> 2.38" }
    random     = { source = "hashicorp/random", version = "~> 3.7" }
    kubectl    = { source = "alekc/kubectl", version = "~> 2.1" }
  }
}
