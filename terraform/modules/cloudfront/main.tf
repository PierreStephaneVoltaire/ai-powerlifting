resource "aws_cloudfront_origin_access_control" "this" {
  name                              = "${var.distribution_name}-oac"
  origin_access_control_origin_type = "s3"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

data "aws_cloudfront_cache_policy" "caching_optimized" {
  name = "Managed-CachingOptimized"
}

resource "aws_cloudfront_response_headers_policy" "immutable_thumbnails" {
  name = "${var.distribution_name}-immutable-thumbnails"

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "public, max-age=31536000, immutable"
      override = true
    }
  }
}

resource "aws_cloudfront_response_headers_policy" "signed_videos" {
  name = "${var.distribution_name}-signed-videos"

  custom_headers_config {
    items {
      header   = "Cache-Control"
      value    = "private, max-age=${var.video_url_ttl_seconds}"
      override = true
    }
  }
}

resource "aws_cloudfront_distribution" "this" {
  origin {
    domain_name              = var.session_videos_bucket_regional_domain_name
    origin_id                = var.session_videos_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  origin {
    domain_name              = var.budget_media_bucket_regional_domain_name
    origin_id                = var.budget_media_origin_id
    origin_access_control_id = aws_cloudfront_origin_access_control.this.id
  }

  enabled         = true
  is_ipv6_enabled = true
  price_class     = "PriceClass_100"

  ordered_cache_behavior {
    path_pattern               = "thumbnails/*"
    target_origin_id           = var.session_videos_origin_id
    viewer_protocol_policy     = "https-only"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.immutable_thumbnails.id
  }

  ordered_cache_behavior {
    path_pattern           = "budget/*"
    target_origin_id       = var.budget_media_origin_id
    viewer_protocol_policy = "https-only"
    allowed_methods        = ["GET", "HEAD"]
    cached_methods         = ["GET", "HEAD"]
    compress               = true
    cache_policy_id        = data.aws_cloudfront_cache_policy.caching_optimized.id
    trusted_key_groups     = [aws_cloudfront_key_group.media.id]
  }

  default_cache_behavior {
    target_origin_id           = var.session_videos_origin_id
    viewer_protocol_policy     = "https-only"
    allowed_methods            = ["GET", "HEAD"]
    cached_methods             = ["GET", "HEAD"]
    compress                   = true
    cache_policy_id            = data.aws_cloudfront_cache_policy.caching_optimized.id
    response_headers_policy_id = aws_cloudfront_response_headers_policy.signed_videos.id
    trusted_key_groups         = [aws_cloudfront_key_group.media.id]
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

# Session videos bucket policy granting CloudFront OAC read access.
resource "aws_s3_bucket_policy" "session_videos" {
  bucket = var.session_videos_bucket_id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid       = "AllowCloudFrontOAC"
      Effect    = "Allow"
      Principal = { Service = "cloudfront.amazonaws.com" }
      Action    = ["s3:GetObject"]
      Resource  = "${var.session_videos_bucket_arn}/*"
      Condition = {
        StringEquals = {
          "AWS:SourceArn" = aws_cloudfront_distribution.this.arn
        }
      }
    }]
  })
}
