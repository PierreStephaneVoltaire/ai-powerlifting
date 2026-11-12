provider "aws" {
  region = var.region
}

provider "kubernetes" {}

provider "helm" {
  kubernetes {}
}
