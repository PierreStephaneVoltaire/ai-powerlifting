output "backend_repository_url" {
  value = module.ecr.repository_urls["powerlifting-app-backend"]
}

output "frontend_repository_url" {
  value = module.ecr.repository_urls["powerlifting-app-frontend"]
}

output "session_videos_bucket_id" {
  value = module.session_videos.bucket_id
}

output "budget_media_bucket_id" {
  value = module.budget_media.bucket_id
}

output "cloudfront_distribution_id" {
  value = module.cloudfront.distribution_id
}

output "cloudfront_media_domain" {
  value = module.cloudfront.distribution_domain_name
}

output "cloudfront_media_base_url" {
  value = "https://${module.cloudfront.distribution_domain_name}"
}

output "video_thumbnail_function_name" {
  value = module.video_thumbnail_lambda.function_name
}
