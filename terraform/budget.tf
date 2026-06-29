resource "aws_s3_bucket" "budget_media" {
  bucket = "powerlifting-budget-media"

  tags = {
    Project = "powerlifting-app"
    Service = "budget-media"
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "budget_media" {
  bucket = aws_s3_bucket.budget_media.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_public_access_block" "budget_media" {
  bucket                  = aws_s3_bucket.budget_media.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_cors_configuration" "budget_media_cors" {
  bucket = aws_s3_bucket.budget_media.id

  cors_rule {
    allowed_headers = ["*"]
    allowed_methods = ["PUT", "GET", "DELETE"]
    allowed_origins = ["*"]
    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "budget_media_lifecycle" {
  bucket = aws_s3_bucket.budget_media.id

  rule {
    id     = "transition-to-ia"
    status = "Enabled"

    filter {
      prefix = "budget/"
    }

    transition {
      days          = 90
      storage_class = "STANDARD_IA"
    }
  }
}

resource "aws_s3_bucket_policy" "budget_media_cloudfront" {
  bucket = aws_s3_bucket.budget_media.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = ["s3:GetObject"]
      Resource  = "${aws_s3_bucket.budget_media.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.session_videos.arn
        }
      }
    }]
  })
}

resource "aws_dynamodb_table" "powerlifting_budget" {
  name         = "if-powerlifting-budget"
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

  tags = {
    Project = "powerlifting-app"
    Service = "budget"
  }
}
