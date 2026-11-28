data "aws_caller_identity" "current" {}
resource "kubernetes_secret_v1" "nth" {
  metadata {
    name      = "node-termination-handler-aws"
    namespace = "kube-system"
  }
  data = {
    role_arn  = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:role/nolift-aws-node-termination-handler"
    queue_url = "https://sqs.${var.region}.amazonaws.com/${data.aws_caller_identity.current.account_id}/nolift-k3s-interruptions"
    region    = var.region
  }
}
