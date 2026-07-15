data "aws_caller_identity" "current" {}

# The lambda source lives in the repo at lambda/video-thumbnail, three
# directories up from this module (terraform/modules/video_thumbnail_lambda).
# The output zip is written to .terraform/ inside the module dir so the
# committed video-thumbnail.zip in the repo root is never overwritten.
data "archive_file" "lambda" {
  type        = "zip"
  output_path = "${path.module}/.terraform/video-thumbnail.zip"
  source_dir  = "${path.module}/../../../lambda/video-thumbnail"
}

# The prebuilt ffmpeg layer is committed alongside this module so the
# module is self-contained and the pipeline doesn't need to walk up the
# repository tree to find it.
locals {
  ffmpeg_layer_path = "${path.module}/ffmpeg-layer.zip"
}

resource "aws_iam_role" "this" {
  name = var.lambda_role_name

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRole"
      Effect    = "Allow"
      Principal = { Service = "lambda.amazonaws.com" }
    }]
  })

  tags = {
    Project = "powerlifting-app"
  }
}

resource "aws_iam_role_policy" "this" {
  name = "${var.lambda_role_name}-policy"
  role = aws_iam_role.this.id

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
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:DeleteObject"]
        Resource = "${var.videos_bucket_arn}/videos/*"
      },
      {
        Effect = "Allow"
        Action = ["s3:PutObject"]
        Resource = [
          "${var.videos_bucket_arn}/thumbnails/*",
          "${var.videos_bucket_arn}/processed/*",
        ]
      },
      {
        Effect = "Allow"
        Action = ["dynamodb:UpdateItem", "dynamodb:Query", "dynamodb:GetItem"]
        Resource = [
          "arn:aws:dynamodb:${var.region}:*:table/${var.health_table_name}",
          "arn:aws:dynamodb:${var.region}:*:table/${var.sessions_table_name}",
        ]
      },
    ]
  })
}

resource "aws_lambda_layer_version" "ffmpeg" {
  filename            = local.ffmpeg_layer_path
  layer_name          = "ffmpeg-layer"
  source_code_hash    = filebase64sha256(local.ffmpeg_layer_path)
  compatible_runtimes = ["python3.12"]
}

resource "aws_lambda_function" "this" {
  function_name = var.function_name
  role          = aws_iam_role.this.arn
  handler       = "index.handler"
  runtime       = "python3.12"
  memory_size   = 2048
  timeout       = 900

  filename         = data.archive_file.lambda.output_path
  source_code_hash = data.archive_file.lambda.output_base64sha256

  layers = [aws_lambda_layer_version.ffmpeg.arn]

  environment {
    variables = {
      TABLE_NAME          = var.health_table_name
      SESSIONS_TABLE_NAME = var.sessions_table_name
      VIDEOS_BUCKET       = var.videos_bucket_id
    }
  }

  tags = {
    Project = "powerlifting-app"
  }
}

resource "aws_lambda_permission" "s3_invoke" {
  statement_id   = "AllowS3Invoke"
  action         = "lambda:InvokeFunction"
  function_name  = aws_lambda_function.this.function_name
  principal      = "s3.amazonaws.com"
  source_arn     = var.videos_bucket_arn
  source_account = data.aws_caller_identity.current.account_id
}

resource "aws_s3_bucket_notification" "session_videos" {
  bucket = var.videos_bucket_id

  lambda_function {
    lambda_function_arn = aws_lambda_function.this.arn
    events              = ["s3:ObjectCreated:*"]
    filter_prefix       = "videos/"
  }

  depends_on = [aws_lambda_permission.s3_invoke]
}
