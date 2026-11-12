provider "aws" {
  region = var.region
}

provider "kubernetes" {}

provider "helm" {
  kubernetes {}
}

provider "kubectl" {}

data "kubernetes_service_v1" "authentik_server" {
  metadata {
    name      = "authentik-server"
    namespace = var.namespace
  }
}

provider "authentik" {
  url      = "http://${data.kubernetes_service_v1.authentik_server.spec[0].cluster_ip}"
  token    = var.authentik_bootstrap_token
  insecure = true
}
