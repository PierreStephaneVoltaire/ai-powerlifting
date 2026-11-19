resource "aws_iam_role_policy" "reference_reader_credentials" {
  name = "powerlifting-reference-reader-credentials"
  role = var.ci_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = "ssm:GetParameter"
      Resource = "arn:aws:ssm:${var.region}:${local.account}:parameter/powerlifting/reference-reader/aws-credentials"
    }]
  })
}
