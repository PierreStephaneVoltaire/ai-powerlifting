resource "aws_cloudfront_origin_access_control" "session_videos" {
  name                              = "powerlifting-session-videos-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

data "aws_cloudfront_origin_request_policy" "all_viewer_except_host_header" {
  name = "Managed-AllViewerExceptHostHeader"
}

resource "aws_cloudfront_distribution" "session_videos" {
  origin {
    domain_name              = aws_s3_bucket.session_videos.bucket_regional_domain_name
    origin_id                = "powerlifting-session-videos"
    origin_access_control_id = aws_cloudfront_origin_access_control.session_videos.id
  }
  origin {
    domain_name              = aws_s3_bucket.budget_media.bucket_regional_domain_name
    origin_id                = "powerlifting-budget-media"
    origin_access_control_id = aws_cloudfront_origin_access_control.session_videos.id
  }

  enabled         = true
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"

  ordered_cache_behavior {
    path_pattern             = "budget/*"
    target_origin_id         = "powerlifting-budget-media"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_optimized.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header.id
  }

  default_cache_behavior {
    target_origin_id         = "powerlifting-session-videos"
    viewer_protocol_policy   = "https-only"
    allowed_methods          = ["GET", "HEAD"]
    cached_methods           = ["GET", "HEAD"]
    compress                 = true
    cache_policy_id          = data.aws_cloudfront_cache_policy.caching_optimized.id
    origin_request_policy_id = data.aws_cloudfront_origin_request_policy.all_viewer_except_host_header.id
  }

  restrictions {
    geo_restriction {
      restriction_type = "none"
    }
  }

  viewer_certificate {
    cloudfront_default_certificate = true
  }
}

resource "aws_s3_bucket_policy" "session_videos_cloudfront" {
  bucket = aws_s3_bucket.session_videos.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = ["s3:GetObject"]
      Resource  = "${aws_s3_bucket.session_videos.arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.session_videos.arn
        }
      }
    }]
  })
}

resource "aws_s3_bucket_public_access_block" "session_videos" {
  bucket = aws_s3_bucket.session_videos.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
