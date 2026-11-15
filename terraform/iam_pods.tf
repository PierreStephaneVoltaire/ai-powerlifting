resource "aws_iam_user" "powerlifting_pods" {
  name = "powerlifting-pods"
}

resource "aws_iam_user_policy" "powerlifting_pods_access" {
  name = "powerlifting-pods-access"
  user = aws_iam_user.powerlifting_pods.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
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
        Resource = [
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-health",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-health/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-health-templates",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-health-templates/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-sessions",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-sessions/index/*",
          module.powerlifting_dynamodb.workout_videos_table_arn,
          "${module.powerlifting_dynamodb.workout_videos_table_arn}/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-user",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-user/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-proposals",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-proposals/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-powerlifting-*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-webhooks",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          "arn:aws:s3:::powerlifting-session-videos",
          "arn:aws:s3:::powerlifting-budget-media",
          "arn:aws:s3:::powerlifting-data-2b0f699b",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:AbortMultipartUpload",
          "s3:ListMultipartUploadParts",
        ]
        Resource = [
          "arn:aws:s3:::powerlifting-session-videos/*",
          "arn:aws:s3:::powerlifting-budget-media/*",
          "arn:aws:s3:::powerlifting-data-2b0f699b/*",
        ]
      },
      {
        Effect   = "Allow"
        Action   = "ecr:GetAuthorizationToken"
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "ecr:BatchCheckLayerAvailability",
          "ecr:BatchGetImage",
          "ecr:GetDownloadUrlForLayer",
        ]
        Resource = "arn:aws:ecr:ca-central-1:429310424269:repository/if-powerlifting-*"
      },
    ]
  })
}
