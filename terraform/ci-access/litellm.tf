data "aws_caller_identity" "current" {}

locals {
  account = data.aws_caller_identity.current.account_id
}

resource "aws_iam_role_policy" "litellm" {
  name = "powerlifting-litellm-ssm"
  role = var.ci_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = ["ssm:GetParametersByPath", "ssm:DeleteParameter"]
        Resource = [
          "arn:aws:ssm:${var.region}:${local.account}:parameter/powerlifting/litellm",
          "arn:aws:ssm:${var.region}:${local.account}:parameter/powerlifting/litellm/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["secretsmanager:DescribeSecret", "secretsmanager:GetSecretValue", "secretsmanager:GetResourcePolicy", "secretsmanager:DeleteSecret"]
        Resource = "arn:aws:secretsmanager:${var.region}:${local.account}:secret:powerlifting/litellm-*"
      },
    ]
  })
}
