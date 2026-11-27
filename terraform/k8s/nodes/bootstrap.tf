data "kubernetes_nodes" "all" {}
locals { control_plane = one([for node in data.kubernetes_nodes.all.nodes : node if contains(keys(node.metadata[0].labels), "node-role.kubernetes.io/control-plane")]) }
resource "random_string" "token_id" {
  length  = 6
  upper   = false
  special = false
  numeric = true
}
resource "random_string" "token_secret" {
  length  = 16
  upper   = false
  special = false
  numeric = true
}
resource "kubernetes_secret_v1" "bootstrap" {
  metadata {
    name      = "bootstrap-token-${random_string.token_id.result}"
    namespace = "kube-system"
  }
  type = "bootstrap.kubernetes.io/token"
  data = {
    token-id                       = random_string.token_id.result
    token-secret                   = random_string.token_secret.result
    usage-bootstrap-authentication = "true"
    usage-bootstrap-signing        = "true"
    auth-extra-groups              = "system:bootstrappers:k3s:default-node-token"
  }
}
resource "aws_ssm_parameter" "server_url" {
  lifecycle { prevent_destroy = true }
  name  = "/nolift/k3s/server-url"
  type  = "String"
  value = "https://nolift-k3s-server:6443"
}
resource "aws_ssm_parameter" "version" {
  lifecycle { prevent_destroy = true }
  name  = "/nolift/k3s/version"
  type  = "String"
  value = local.control_plane.status[0].node_info[0].kubelet_version
}

data "http" "cacerts" {
  url         = "https://kubernetes.default.svc/cacerts"
  ca_cert_pem = try(file("/var/run/secrets/kubernetes.io/serviceaccount/ca.crt"), null)
}
resource "aws_ssm_parameter" "agent_token" {
  lifecycle { prevent_destroy = true }
  name       = "/nolift/k3s/agent-token"
  type       = "SecureString"
  value      = "K10${sha256(data.http.cacerts.response_body)}::${random_string.token_id.result}.${random_string.token_secret.result}"
  depends_on = [kubernetes_secret_v1.bootstrap]
}
