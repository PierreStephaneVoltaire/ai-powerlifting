output "backend_repository_url" {
  value = aws_ecr_repository.powerlifting_backend.repository_url
}

output "frontend_repository_url" {
  value = aws_ecr_repository.powerlifting_frontend.repository_url
}

output "cloudfront_media_domain" {
  description = "CloudFront domain serving the powerlifting session videos bucket"
  value       = aws_cloudfront_distribution.session_videos.domain_name
}

output "cloudfront_media_base_url" {
  description = "Full https URL for CloudFront media distribution (used as VITE_CLOUDFRONT_MEDIA_BASE_URL)"
  value       = "https://${aws_cloudfront_distribution.session_videos.domain_name}"
}
