###############################################################################
# ECR repositories for backend and frontend container images.
###############################################################################
module "ecr" {
  source = "./modules/ecr"

  repository_prefix = var.ecr_repository_prefix
  repository_names  = ["powerlifting-app-backend", "powerlifting-app-frontend"]
}

###############################################################################
# Session videos S3 bucket (uploaded by the app) + the ffmpeg Lambda that
# generates thumbnails on object-created.
###############################################################################
module "session_videos" {
  source = "./modules/session_videos"

  bucket_name = "powerlifting-session-videos"
}

module "video_thumbnail_lambda" {
  source = "./modules/video_thumbnail_lambda"

  function_name       = "video-thumbnail-generator"
  lambda_role_name    = "video-thumbnail-lambda-role"
  region              = var.region
  videos_bucket_id    = module.session_videos.bucket_id
  videos_bucket_arn   = module.session_videos.bucket_arn
  health_table_name   = var.dynamodb_health_table
  sessions_table_name = var.dynamodb_sessions_table
}

###############################################################################
# CloudFront distribution fronting the session videos bucket (default) and
# the budget media bucket (path pattern: budget/*).
###############################################################################
module "cloudfront" {
  source = "./modules/cloudfront"

  distribution_name = "powerlifting-session-videos"

  session_videos_bucket_id                   = module.session_videos.bucket_id
  session_videos_bucket_arn                  = module.session_videos.bucket_arn
  session_videos_bucket_regional_domain_name = module.session_videos.bucket_regional_domain_name
  session_videos_origin_id                   = "powerlifting-session-videos"

  budget_media_bucket_regional_domain_name = module.budget_media.bucket_regional_domain_name
  budget_media_origin_id                    = "powerlifting-budget-media"
}

###############################################################################
# Budget media S3 bucket (depends on the CloudFront ARN it can read from).
###############################################################################
module "budget_media" {
  source = "./modules/budget_media"

  bucket_name                 = "powerlifting-budget-media"
  cloudfront_distribution_arn = module.cloudfront.distribution_arn
}
