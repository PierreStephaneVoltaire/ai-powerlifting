output "backend_repository_url" {
  value = aws_ecr_repository.powerlifting_backend.repository_url
}

output "frontend_repository_url" {
  value = aws_ecr_repository.powerlifting_frontend.repository_url
}

output "cloudfront_media_domain" {
  value = aws_cloudfront_distribution.session_videos.domain_name
}

output "cloudfront_media_base_url" {
  value = "https://${aws_cloudfront_distribution.session_videos.domain_name}"
}
