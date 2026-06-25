resource "aws_s3_bucket" "session_videos" {
  bucket = "powerlifting-session-videos"

  tags = {
    Project = "powerlifting-app"
    Service = "video-storage"
  }
}

# Explicit SSE-S3 (AES256) encryption. Pinned to Amazon S3-managed keys so
# the bucket stays encrypted at rest WITHOUT any KMS API calls per request.
# This overrides any account-level default-encryption setting that might
# otherwise attach a customer-managed KMS key and rack up per-PUT/GET KMS fees
# (the video-thumbnail Lambda does head_object + download_file + 2x put_object
# + delete_object per upload, so a CMK here would be expensive).
resource "aws_s3_bucket_server_side_encryption_configuration" "session_videos" {
  bucket = aws_s3_bucket.session_videos.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
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
        Action   = ["s3:GetObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.session_videos.arn}/videos/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "${aws_s3_bucket.session_videos.arn}/thumbnails/*",
          "${aws_s3_bucket.session_videos.arn}/processed/*"
        ]
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:GetItem"]
        Resource = [
          "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_health_table}",
          "arn:aws:dynamodb:${var.region}:*:table/${var.dynamodb_sessions_table}"
        ]
      }
    ]
  })
}

data "aws_caller_identity" "current" {}

data "archive_file" "video_lambda" {
  type        = "zip"
  output_path = "${path.module}/video-lambda.zip"
  source_dir  = "${path.module}/../video-lambda"
}

resource "aws_lambda_layer_version" "ffmpeg" {
  filename            = "${path.module}/ffmpeg-layer.zip"
  layer_name          = "ffmpeg-layer"
  source_code_hash    = filebase64sha256("${path.module}/ffmpeg-layer.zip")
  compatible_runtimes = ["python3.12"]
}

resource "aws_lambda_function" "video_thumbnail" {
  function_name = "video-thumbnail-generator"
  role          = aws_iam_role.video_thumbnail_lambda.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  memory_size   = 2048
  timeout       = 900

  filename         = data.archive_file.video_lambda.output_path
  source_code_hash = data.archive_file.video_lambda.output_base64sha256

  layers = [aws_lambda_layer_version.ffmpeg.arn]

  environment {
    variables = {
      TABLE_NAME          = var.dynamodb_health_table
      SESSIONS_TABLE_NAME = var.dynamodb_sessions_table
      VIDEOS_BUCKET       = aws_s3_bucket.session_videos.id
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
