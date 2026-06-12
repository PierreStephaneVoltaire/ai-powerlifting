# ─── Powerlifting master -> user sync Lambda ────────────────────────────────
# Triggered by DynamoDB streams on the two master powerlifting tables; fans
# master-owned fields out to per-user copies. See
# utils/powerlifting-app/lambda/master-sync/handler.py for the fan-out logic.

data "aws_caller_identity" "powerlifting_master_sync" {}

# ─── Lambda zip ─────────────────────────────────────────────────────────────
# We re-use the same archive_file pattern as the video lambda. The handler
# has no third-party deps beyond boto3, which is in the Python 3.12 runtime.
data "archive_file" "powerlifting_master_sync" {
  type        = "zip"
  output_path = "${path.module}/powerlifting-master-sync.zip"
  source_dir  = "${path.module}/../utils/powerlifting-app/lambda/master-sync"
}

# ─── DLQ for stream failures ────────────────────────────────────────────────
resource "aws_sqs_queue" "powerlifting_master_sync_dlq" {
  name                      = "powerlifting-master-sync-dlq"
  message_retention_seconds = 1209600 # 14 days

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-sync"
  }
}

# ─── IAM role ───────────────────────────────────────────────────────────────
resource "aws_iam_role" "powerlifting_master_sync_lambda" {
  name = "powerlifting-master-sync-lambda-role"

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
    Project = "if-prototype-a1"
    Service = "powerlifting-master-sync"
  }
}

resource "aws_iam_role_policy" "powerlifting_master_sync_lambda" {
  name = "powerlifting-master-sync-lambda-policy"
  role = aws_iam_role.powerlifting_master_sync_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents",
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:DescribeStream",
          "dynamodb:GetRecords",
          "dynamodb:GetShardIterator",
          "dynamodb:ListStreams",
        ]
        Resource = [
          aws_dynamodb_table.if_powerlifting_master_competitions.stream_arn,
          aws_dynamodb_table.if_powerlifting_master_federations.stream_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
        ]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_user_table}"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:BatchGetItem",
          "dynamodb:BatchWriteItem",
          "dynamodb:GetItem",
          "dynamodb:PutItem",
          "dynamodb:UpdateItem",
          "dynamodb:Query",
        ]
        Resource = [
          "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_powerlifting_user_competitions_table}",
          "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_powerlifting_user_federations_table}",
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "sqs:SendMessage",
        ]
        Resource = aws_sqs_queue.powerlifting_master_sync_dlq.arn
      },
    ]
  })
}

# ─── Lambda function ────────────────────────────────────────────────────────
resource "aws_lambda_function" "powerlifting_master_sync" {
  function_name = "powerlifting-master-sync"
  role          = aws_iam_role.powerlifting_master_sync_lambda.arn
  handler       = "handler.handler"
  runtime       = "python3.12"
  memory_size   = 256
  timeout       = 60

  filename         = data.archive_file.powerlifting_master_sync.output_path
  source_code_hash = data.archive_file.powerlifting_master_sync.output_base64sha256

  environment {
    variables = {
      # NOTE: AWS_REGION is reserved by the Lambda runtime and is set
      # automatically. We must NOT override it here or the function
      # fails to start.
      COMP_MASTER_TABLE = var.dynamodb_powerlifting_master_competitions_table
      COMP_USER_TABLE   = var.dynamodb_powerlifting_user_competitions_table
      FED_MASTER_TABLE  = var.dynamodb_powerlifting_master_federations_table
      FED_USER_TABLE    = var.dynamodb_powerlifting_user_federations_table
      USER_INDEX_TABLE  = var.dynamodb_user_table
    }
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-sync"
  }
}

# ─── Event source mappings (one per master table) ──────────────────────────
resource "aws_lambda_event_source_mapping" "powerlifting_master_competitions" {
  event_source_arn               = aws_dynamodb_table.if_powerlifting_master_competitions.stream_arn
  function_name                  = aws_lambda_function.powerlifting_master_sync.arn
  starting_position              = "TRIM_HORIZON"
  batch_size                     = 25
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 3

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.powerlifting_master_sync_dlq.arn
    }
  }
}

resource "aws_lambda_event_source_mapping" "powerlifting_master_federations" {
  event_source_arn               = aws_dynamodb_table.if_powerlifting_master_federations.stream_arn
  function_name                  = aws_lambda_function.powerlifting_master_sync.arn
  starting_position              = "TRIM_HORIZON"
  batch_size                     = 25
  bisect_batch_on_function_error = true
  maximum_retry_attempts         = 3

  destination_config {
    on_failure {
      destination_arn = aws_sqs_queue.powerlifting_master_sync_dlq.arn
    }
  }
}
