locals {
  pods_user_arn      = "arn:aws:iam::${local.account}:user/powerlifting-pods"
  reference_read_arn = "arn:aws:iam::${local.account}:policy/powerlifting-reference-read"
}

import {
  to = aws_iam_role_policy.powerlifting_pods
  id = "${var.ci_role_name}:powerlifting-pods-terraform"
}

resource "aws_iam_role_policy" "powerlifting_pods" {
  name = "powerlifting-pods-terraform"
  role = var.ci_role_name

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "iam:GetUser",
          "iam:ListUserTags",
          "iam:ListUserPolicies",
          "iam:GetUserPolicy",
          "iam:PutUserPolicy",
          "iam:ListAttachedUserPolicies",
        ]
        Resource = local.pods_user_arn
      },
      {
        Effect    = "Allow"
        Action    = "iam:AttachUserPolicy"
        Resource  = local.pods_user_arn
        Condition = { ArnEquals = { "iam:PolicyARN" = local.reference_read_arn } }
      },
      {
        Effect = "Allow"
        Action = [
          "iam:CreatePolicy",
          "iam:CreatePolicyVersion",
          "iam:GetPolicy",
          "iam:GetPolicyVersion",
          "iam:ListPolicyTags",
          "iam:ListPolicyVersions",
        ]
        Resource = local.reference_read_arn
      },
    ]
  })
}
