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

locals {
  reference_prefixes = ["references/supplements/*", "references/federation-rules/*"]
}

resource "aws_iam_policy" "reference_read" {
  name = "powerlifting-reference-read"

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect    = "Allow"
        Action    = "s3:ListBucketVersions"
        Resource  = aws_s3_bucket.reference_documents.arn
        Condition = { StringLike = { "s3:prefix" = local.reference_prefixes } }
      },
      {
        Effect   = "Allow"
        Action   = "s3:GetObjectVersion"
        Resource = [for prefix in local.reference_prefixes : "${aws_s3_bucket.reference_documents.arn}/${prefix}"]
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "reference_read" {
  user       = aws_iam_user.powerlifting_pods.name
  policy_arn = aws_iam_policy.reference_read.arn
}
