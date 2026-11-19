resource "aws_s3_bucket" "reference_documents" {
  bucket = "powerlifting-reference-documents-429310424269-ca-central-1"

  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "reference_documents" {
  bucket = aws_s3_bucket.reference_documents.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_public_access_block" "reference_documents" {
  bucket                  = aws_s3_bucket.reference_documents.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_server_side_encryption_configuration" "reference_documents" {
  bucket = aws_s3_bucket.reference_documents.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}
