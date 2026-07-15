data "aws_caller_identity" "current" {}

data "aws_dynamodb_table" "master_competitions" {
  name = "if-powerlifting-master-competitions"
}

data "aws_dynamodb_table" "master_federations" {
  name = "if-powerlifting-master-federations"
}

data "archive_file" "powerlifting_master_sync" {
  type        = "zip"
  output_path = "${path.module}/.terraform/powerlifting-master-sync.zip"
  source_dir  = "${path.module}/../../../lambda/master-sync"
}

resource "aws_sqs_queue" "powerlifting_master_sync_dlq" {
  name                      = "powerlifting-master-sync-dlq"
  message_retention_seconds = 1209600

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-sync"
  }
}

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
          data.aws_dynamodb_table.master_competitions.stream_arn,
          data.aws_dynamodb_table.master_federations.stream_arn,
        ]
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:Scan",
        ]
        Resource = "arn:aws:dynamodb:ca-central-1:*:table/if-user"
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
          "arn:aws:dynamodb:ca-central-1:*:table/if-powerlifting-user-competitions",
          "arn:aws:dynamodb:ca-central-1:*:table/if-powerlifting-user-federations",
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
      COMP_MASTER_TABLE = "if-powerlifting-master-competitions"
      COMP_USER_TABLE   = "if-powerlifting-user-competitions"
      FED_MASTER_TABLE  = "if-powerlifting-master-federations"
      FED_USER_TABLE    = "if-powerlifting-user-federations"
      USER_INDEX_TABLE  = "if-user"
    }
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-sync"
  }
}

resource "aws_lambda_event_source_mapping" "powerlifting_master_competitions" {
  event_source_arn               = data.aws_dynamodb_table.master_competitions.stream_arn
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
  event_source_arn               = data.aws_dynamodb_table.master_federations.stream_arn
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
