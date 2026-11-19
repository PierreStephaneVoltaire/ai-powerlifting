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
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-health-templates",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-sessions",
          module.powerlifting_dynamodb.workout_videos_table_arn,
          "${module.powerlifting_dynamodb.workout_videos_table_arn}/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-user",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-proposals",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-proposals/index/*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-powerlifting-*",
          "arn:aws:dynamodb:ca-central-1:429310424269:table/if-webhooks",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
        ]
        Resource = module.powerlifting_dynamodb.supplements_table_arn
      },
      {
        Effect = "Allow"
        Action = [
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          "arn:aws:s3:::powerlifting-session-videos",
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

resource "aws_iam_user" "reference_reader" {
  name = "powerlifting-reference-reader"
}

resource "aws_iam_user_policy" "reference_reader" {
  name = "powerlifting-reference-reader"
  user = aws_iam_user.reference_reader.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "s3:ListBucketVersions"
        Resource = aws_s3_bucket.reference_documents.arn
        Condition = {
          StringLike = {
            "s3:prefix" = [
              "references/supplements/*",
              "references/federation-rules/*",
            ]
          }
        }
      },
      {
        Effect = "Allow"
        Action = "s3:GetObjectVersion"
        Resource = [
          "${aws_s3_bucket.reference_documents.arn}/references/supplements/*",
          "${aws_s3_bucket.reference_documents.arn}/references/federation-rules/*",
        ]
      },
    ]
  })
}

resource "aws_iam_access_key" "reference_reader" {
  user = aws_iam_user.reference_reader.name
}

resource "aws_ssm_parameter" "reference_reader_credentials" {
  name = "/powerlifting/reference-reader/aws-credentials"
  type = "SecureString"
  value = jsonencode({
    access_key_id     = aws_iam_access_key.reference_reader.id
    secret_access_key = aws_iam_access_key.reference_reader.secret
  })
}
