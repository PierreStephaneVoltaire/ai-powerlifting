module "ecr" {
  source = "./modules/ecr"

  repository_prefix                = "if"
  repository_names                 = ["powerlifting-app-backend", "powerlifting-app-frontend", "powerlifting-analytics", "powerlifting-coach-agent", "powerlifting-coach-discord", "powerlifting-fns"]
  untagged_expiry_repository_names = ["powerlifting-fns"]
}

module "session_videos" {
  source = "./modules/session_videos"

  bucket_name = "powerlifting-session-videos"
}

module "video_thumbnail_lambda" {
  source = "./modules/video_thumbnail_lambda"

  function_name       = "video-thumbnail-generator"
  lambda_role_name    = "video-thumbnail-lambda-role"
  region              = "ca-central-1"
  videos_bucket_id    = module.session_videos.bucket_id
  videos_bucket_arn   = module.session_videos.bucket_arn
  health_table_name   = "if-health"
  sessions_table_name = "if-sessions"
}

module "cloudfront" {
  source = "./modules/cloudfront"

  distribution_name = "powerlifting-session-videos"

  session_videos_bucket_id                   = module.session_videos.bucket_id
  session_videos_bucket_arn                  = module.session_videos.bucket_arn
  session_videos_bucket_regional_domain_name = module.session_videos.bucket_regional_domain_name
  session_videos_origin_id                   = "powerlifting-session-videos"

  budget_media_bucket_regional_domain_name = module.budget_media.bucket_regional_domain_name
  budget_media_origin_id                   = "powerlifting-budget-media"
}

module "budget_media" {
  source = "./modules/budget_media"

  bucket_name                 = "powerlifting-budget-media"
  cloudfront_distribution_arn = module.cloudfront.distribution_arn
}

module "powerlifting_dynamodb" {
  source = "./modules/powerlifting_dynamodb"
}

module "powerlifting_dataset" {
  source = "./modules/powerlifting_dataset"
}

module "powerlifting_master_sync" {
  source = "./modules/powerlifting_master_sync"
}

module "tunnel" {
  source = "./modules/tunnel"

  account_id           = var.cloudflare_account_id
  name                 = "powerlifting"
  zone                 = var.app_zone
  hostname             = var.app_domain
  origin_url           = var.tunnel_origin_url
  zone_plan            = var.cloudflare_zone_plan
  auth_hostname        = var.auth_domain
  auth_origin_url      = var.tunnel_origin_url
  token_parameter_name = "/powerlifting/k8s/tunnel-token"
}
