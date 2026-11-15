data "aws_caller_identity" "current" {}

data "aws_region" "current" {}

locals {
  log_group_arn = "arn:aws:logs:${data.aws_region.current.region}:${data.aws_caller_identity.current.account_id}:log-group:/aws/lambda/${var.function_name}"
}

resource "aws_iam_role" "this" {
  name                 = "${var.function_name}-role"
  permissions_boundary = "arn:aws:iam::${data.aws_caller_identity.current.account_id}:policy/${var.function_name}-boundary"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-glossary-catalog"
  }
}

resource "aws_iam_role_policy" "this" {
  name = "${var.function_name}-policy"
  role = aws_iam_role.this.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = "logs:CreateLogGroup"
        Resource = local.log_group_arn
      },
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "${local.log_group_arn}:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
        ]
        Resource = var.stream_arn
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:ListStreams"]
        Resource = "*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:ConditionCheckItem",
        ]
        Resource = var.table_arn
      },
    ]
  })
}

resource "aws_lambda_function" "this" {
  function_name    = var.function_name
  role             = aws_iam_role.this.arn
  runtime          = "provided.al2023"
  architectures    = ["arm64"]
  handler          = "bootstrap"
  memory_size      = 128
  timeout          = 30
  filename         = var.zip_path
  source_code_hash = filebase64sha256(var.zip_path)

  environment {
    variables = {
      GLOSSARY_TABLE_NAME = var.table_name
    }
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-glossary-catalog"
  }
}

resource "aws_lambda_event_source_mapping" "this" {
  event_source_arn                   = var.stream_arn
  function_name                      = aws_lambda_function.this.arn
  starting_position                  = "TRIM_HORIZON"
  batch_size                         = 25
  maximum_batching_window_in_seconds = 1
  maximum_retry_attempts             = 5
  function_response_types            = ["ReportBatchItemFailures"]

  filter_criteria {
    filter {
      pattern = jsonencode({
        eventName = ["INSERT", "MODIFY"]
        dynamodb = {
          NewImage = {
            pk     = { S = [{ prefix = "ATHLETE#" }] }
            custom = { BOOL = [true] }
          }
        }
      })
    }
  }
}
