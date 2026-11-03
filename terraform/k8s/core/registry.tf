data "aws_ecr_authorization_token" "registry" {}

locals {
  registry_server = replace(data.aws_ecr_authorization_token.registry.proxy_endpoint, "https://", "")
}

resource "kubernetes_secret_v1" "registry" {
  metadata {
    name      = "ecr-registry"
    namespace = kubernetes_namespace_v1.powerlifting.metadata[0].name
  }

  type = "kubernetes.io/dockerconfigjson"

  data = {
    ".dockerconfigjson" = jsonencode({
      auths = {
        (local.registry_server) = {
          username = data.aws_ecr_authorization_token.registry.user_name
          password = data.aws_ecr_authorization_token.registry.password
          auth     = data.aws_ecr_authorization_token.registry.authorization_token
        }
      }
    })
  }

  lifecycle {
    ignore_changes = [data]
  }
}
