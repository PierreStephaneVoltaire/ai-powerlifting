locals {
  glossary_catalog_role_arn     = "arn:aws:iam::${local.account}:role/${var.glossary_catalog_function_name}-role"
  glossary_catalog_boundary_arn = "arn:aws:iam::${local.account}:policy/${var.glossary_catalog_function_name}-boundary"
  glossary_catalog_log_group    = "arn:aws:logs:${var.region}:${local.account}:log-group:/aws/lambda/${var.glossary_catalog_function_name}"
  glossary_table_arn            = "arn:aws:dynamodb:${var.region}:${local.account}:table/${var.glossary_table_name}"
}

resource "aws_iam_policy" "glossary_catalog_boundary" {
  name = "${var.glossary_catalog_function_name}-boundary"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "logs:CreateLogGroup"
        Resource = local.glossary_catalog_log_group
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${local.glossary_catalog_log_group}:*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:DescribeStream", "dynamodb:GetRecords", "dynamodb:GetShardIterator"]
        Resource = "${local.glossary_table_arn}/stream/*"
      },
      {
        Effect   = "Allow"
        Action   = "dynamodb:ListStreams"
        Resource = "*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:PutItem", "dynamodb:ConditionCheckItem"]
        Resource = local.glossary_table_arn
      },
    ]
  })
}

resource "aws_iam_role_policy" "glossary_catalog_lambda" {
  name = "powerlifting-glossary-catalog-lambda"
  role = var.ci_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = ["iam:CreateRole", "iam:PutRolePolicy", "iam:DeleteRolePolicy", "iam:PutRolePermissionsBoundary"]
        Resource  = local.glossary_catalog_role_arn
        Condition = { StringEquals = { "iam:PermissionsBoundary" = local.glossary_catalog_boundary_arn } }
      },
      {
        Effect = "Allow"
        Action = [
          "iam:GetRole",
          "iam:GetRolePolicy",
          "iam:ListRolePolicies",
          "iam:ListAttachedRolePolicies",
          "iam:ListInstanceProfilesForRole",
          "iam:TagRole",
          "iam:UntagRole",
          "iam:DeleteRole",
        ]
        Resource = local.glossary_catalog_role_arn
      },
      {
        Effect    = "Allow"
        Action    = "iam:PassRole"
        Resource  = local.glossary_catalog_role_arn
        Condition = { StringEquals = { "iam:PassedToService" = "lambda.amazonaws.com" } }
      },
      {
        Effect   = "Allow"
        Action   = ["iam:GetPolicy", "iam:GetPolicyVersion"]
        Resource = aws_iam_policy.glossary_catalog_boundary.arn
      },
      {
        Effect   = "Deny"
        Action   = ["iam:DeleteRolePermissionsBoundary", "iam:CreatePolicyVersion", "iam:SetDefaultPolicyVersion", "iam:DeletePolicy"]
        Resource = [local.glossary_catalog_role_arn, aws_iam_policy.glossary_catalog_boundary.arn]
      },
    ]
  })
}
