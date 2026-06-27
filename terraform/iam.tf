# ---------------------------------------------------------------------------
# Phase 3 — Shared Lambda execution role + scoped IAM policy.
#
# One role shared by all 76 health lambdas. The policy grants:
#   - CloudWatch Logs: create log group + streams + put log events
#   - DynamoDB: read/write on the 5 health tables (if-health, if-health-templates,
#               if-sessions, if-powerlifting-analysis-cache, if-proposals)
#   - S3: read-only on the OpenPowerlifting dataset bucket (stats lambdas)
#   - Lambda: invoke (master-sync may chain other lambdas)
# ---------------------------------------------------------------------------

# data.aws_caller_identity.current is declared in videos.tf and reused here.

resource "aws_iam_role" "lambda_exec" {
  name = "powerlifting-lambda-exec-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })

  tags = {
    Project = "powerlifting-app"
    Service = "lambda-exec"
  }
}

# Single inline policy scoped to exactly what the health lambdas need.
# DynamoDB: full item CRUD + query/scan on the 5 health-domain tables.
# S3:      read-only on the OpenPowerlifting dataset bucket (stats Stream B).
# Lambda:  invoke so master-sync can fan out to other pl-* functions.
resource "aws_iam_role_policy" "lambda_exec" {
  name = "powerlifting-lambda-exec-policy"
  role = aws_iam_role.lambda_exec.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "CloudWatchLogs"
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:${var.region}:${data.aws_caller_identity.current.account_id}:*"
      },
      {
        Sid    = "DynamoDBHealthTables"
        Effect = "Allow"
        Action = [
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:DeleteItem",
          "dynamodb:Query",
          "dynamodb:Scan",
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
        ]
        Resource = [
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_health_table}",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_health_table}/index/*",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_templates_table}",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_templates_table}/index/*",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_sessions_table}",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_sessions_table}/index/*",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_analysis_cache_table}",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_analysis_cache_table}/index/*",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_proposals_table}",
          "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.current.account_id}:table/${var.dynamodb_proposals_table}/index/*",
        ]
      },
      {
        Sid    = "S3OpenPowerliftingDatasetRead"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:ListBucket",
        ]
        Resource = [
          "arn:aws:s3:::${var.powerlifting_s3_bucket}",
          "arn:aws:s3:::${var.powerlifting_s3_bucket}/*",
        ]
      },
      {
        Sid    = "LambdaInvoke"
        Effect = "Allow"
        Action = ["lambda:InvokeFunction"]
        # master-sync may fan out to other pl-* health lambdas.
        Resource = "arn:aws:lambda:${var.region}:${data.aws_caller_identity.current.account_id}:function:${var.lambda_function_prefix}*"
      },
    ]
  })
}