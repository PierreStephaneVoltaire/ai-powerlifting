data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  table_arns = [
    for name in var.table_names :
    "arn:aws:dynamodb:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:table/${name}"
  ]
}

resource "aws_iam_user" "pods" {
  name = var.user_name
}

data "aws_iam_policy_document" "pods" {
  statement {
    actions = [
      "dynamodb:BatchGetItem",
      "dynamodb:BatchWriteItem",
      "dynamodb:ConditionCheckItem",
      "dynamodb:DeleteItem",
      "dynamodb:DescribeTable",
      "dynamodb:GetItem",
      "dynamodb:PutItem",
      "dynamodb:Query",
      "dynamodb:Scan",
      "dynamodb:UpdateItem",
    ]
    resources = concat(local.table_arns, [for arn in local.table_arns : "${arn}/index/*"])
  }

  statement {
    actions   = ["s3:ListBucket", "s3:GetBucketLocation"]
    resources = var.bucket_arns
  }

  statement {
    actions = [
      "s3:GetObject",
      "s3:PutObject",
      "s3:DeleteObject",
      "s3:AbortMultipartUpload",
      "s3:ListMultipartUploadParts",
    ]
    resources = [for arn in var.bucket_arns : "${arn}/*"]
  }

  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    actions   = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
    resources = [for name in var.repository_names : "arn:aws:ecr:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:repository/${name}"]
  }
}

resource "aws_iam_user_policy" "pods" {
  name   = "${var.user_name}-access"
  user   = aws_iam_user.pods.name
  policy = data.aws_iam_policy_document.pods.json
}

resource "aws_iam_access_key" "pods" {
  user = aws_iam_user.pods.name
}

resource "aws_ssm_parameter" "pods" {
  name = var.parameter_name
  type = "SecureString"
  value = jsonencode({
    aws_access_key_id     = aws_iam_access_key.pods.id
    aws_secret_access_key = aws_iam_access_key.pods.secret
  })
}
