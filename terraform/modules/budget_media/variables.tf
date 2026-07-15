variable "bucket_name" {
  type        = string
  description = "Name of the S3 bucket that holds budget media."
}

variable "cloudfront_distribution_arn" {
  type        = string
  description = "ARN of the CloudFront distribution allowed to read this bucket."
}
