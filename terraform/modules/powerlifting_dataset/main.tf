resource "aws_s3_bucket" "powerlifting_data" {
  bucket = "powerlifting-data-2b0f699b"

  tags = {
    Name        = "Powerlifting Data Bucket"
    Environment = "production"
    Project     = "powerlifting-portal"
  }
}

resource "aws_s3_bucket_public_access_block" "powerlifting_data_public_block" {
  bucket = aws_s3_bucket.powerlifting_data.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "powerlifting_data" {
  bucket = aws_s3_bucket.powerlifting_data.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
    bucket_key_enabled = false
  }
}

resource "aws_s3_bucket_versioning" "powerlifting_data_versioning" {
  bucket = aws_s3_bucket.powerlifting_data.id
  versioning_configuration {
    status = "Enabled"
  }
}
