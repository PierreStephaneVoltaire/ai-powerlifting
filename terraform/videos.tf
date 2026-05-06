resource "aws_s3_bucket" "session_videos" {
  bucket = "powerlifting-session-videos"

  tags = {
    Project = "powerlifting-app"
    Service = "video-storage"
  }
}

resource "aws_s3_bucket_cors_configuration" "session_videos_cors" {
  bucket = aws_s3_bucket.session_videos.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "DELETE"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "session_videos_lifecycle" {
  bucket = aws_s3_bucket.session_videos.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {
      prefix = "videos/"
    }

    transition {
      days          = 365
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_iam_role" "video_thumbnail_lambda" {
  name = "video-thumbnail-lambda-role"

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
  }
}

resource "aws_iam_role_policy" "video_thumbnail_lambda" {
  name = "video-thumbnail-lambda-policy"
  role = aws_iam_role.video_thumbnail_lambda.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect = "Allow"
        Action = [
          "logs:CreateLogGroup",
          "logs:CreateLogStream",
          "logs:PutLogEvents"
        ]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:GetObject"]
        Resource = "${aws_s3_bucket.session_videos.arn}/videos/*"
      },
      {
        Effect   = "Allow"
        Action   = ["s3:PutObject"]
        Resource = "${aws_s3_bucket.session_videos.arn}/thumbnails/*"
      },
      {
        Effect   = "Allow"
        Action   = ["dynamodb:UpdateItem"]
        Resource = "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_health_table}"
      }
    ]
  })
}

resource "aws_dynamodb_table" "if_models" {
  name         = var.dynamodb_models_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "model-registry"
  }
}

# ─── Existing DynamoDB Tables (imported into Terraform state) ──────────────

resource "aws_dynamodb_table" "if_core" {
  name         = var.dynamodb_core_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "core-directives"
  }
}

resource "aws_dynamodb_table" "if_health" {
  name         = var.dynamodb_health_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "ttl"
    enabled        = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "health"
  }
}

resource "aws_dynamodb_table" "if_sessions" {
  name         = var.dynamodb_sessions_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "sessions"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_analysis_cache" {
  name         = var.dynamodb_analysis_cache_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-analysis-cache"
  }
}

resource "aws_dynamodb_table" "if_finance" {
  name         = var.dynamodb_finance_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "finance"
  }
}

resource "aws_dynamodb_table" "if_diary_entries" {
  name         = var.dynamodb_diary_entries_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "diary"
  }
}

resource "aws_dynamodb_table" "if_diary_signals" {
  name         = var.dynamodb_diary_signals_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "diary-signals"
  }
}

resource "aws_dynamodb_table" "if_proposals" {
  name         = var.dynamodb_proposals_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "proposals"
  }
}

data "aws_caller_identity" "current" {}

data "archive_file" "video_lambda" {
  type        = "zip"
  output_path = "${path.module}/video-lambda.zip"
  source_dir  = "${path.module}/../utils/video-lambda"
}

resource "aws_lambda_function" "video_thumbnail" {
  function_name = "video-thumbnail-generator"
  role          = aws_iam_role.video_thumbnail_lambda.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  memory_size   = 1024
  timeout       = 60

  filename         = data.archive_file.video_lambda.output_path
  source_code_hash = data.archive_file.video_lambda.output_base64sha256

  environment {
    variables = {
      TABLE_NAME    = var.dynamodb_health_table
      VIDEOS_BUCKET = aws_s3_bucket.session_videos.id
    }
  }

  tags = {
    Project = "powerlifting-app"
  }
}

resource "aws_lambda_permission" "s3_invoke" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.video_thumbnail.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = aws_s3_bucket.session_videos.arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "session_videos" {
  bucket = aws_s3_bucket.session_videos.id

  lambda_function {
    lambda_function_arn = aws_lambda_function.video_thumbnail.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "videos/"
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}
