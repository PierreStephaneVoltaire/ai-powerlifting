# ----------------------------------------------------------------------------
# State move map: maps the old root-level resource addresses to the new
# module-prefixed addresses after the terraform/ refactor.
#
# Apply this file once. After `terraform plan` reports 0 changes, you can
# remove this file in a follow-up commit.
# ----------------------------------------------------------------------------

# === ECR (was in main.tf) ===
moved {
  from = aws_ecr_repository.powerlifting_backend
  to   = module.ecr.aws_ecr_repository.this["powerlifting-app-backend"]
}

moved {
  from = aws_ecr_repository.powerlifting_frontend
  to   = module.ecr.aws_ecr_repository.this["powerlifting-app-frontend"]
}

moved {
  from = aws_ecr_lifecycle_policy.keep_5["backend"]
  to   = module.ecr.aws_ecr_lifecycle_policy.keep_5["powerlifting-app-backend"]
}

moved {
  from = aws_ecr_lifecycle_policy.keep_5["frontend"]
  to   = module.ecr.aws_ecr_lifecycle_policy.keep_5["powerlifting-app-frontend"]
}

# === Session videos bucket (was in videos.tf) ===
moved {
  from = aws_s3_bucket.session_videos
  to   = module.session_videos.aws_s3_bucket.this
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.session_videos
  to   = module.session_videos.aws_s3_bucket_server_side_encryption_configuration.this
}

moved {
  from = aws_s3_bucket_cors_configuration.session_videos_cors
  to   = module.session_videos.aws_s3_bucket_cors_configuration.this
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.session_videos_lifecycle
  to   = module.session_videos.aws_s3_bucket_lifecycle_configuration.this
}

moved {
  from = aws_s3_bucket_public_access_block.session_videos
  to   = module.session_videos.aws_s3_bucket_public_access_block.this
}

# === Budget media bucket (was in budget.tf) ===
moved {
  from = aws_s3_bucket.budget_media
  to   = module.budget_media.aws_s3_bucket.this
}

moved {
  from = aws_s3_bucket_server_side_encryption_configuration.budget_media
  to   = module.budget_media.aws_s3_bucket_server_side_encryption_configuration.this
}

moved {
  from = aws_s3_bucket_public_access_block.budget_media
  to   = module.budget_media.aws_s3_bucket_public_access_block.this
}

moved {
  from = aws_s3_bucket_cors_configuration.budget_media_cors
  to   = module.budget_media.aws_s3_bucket_cors_configuration.this
}

moved {
  from = aws_s3_bucket_lifecycle_configuration.budget_media_lifecycle
  to   = module.budget_media.aws_s3_bucket_lifecycle_configuration.this
}

# Note: the old budget.tf had a `aws_s3_bucket_policy.budget_media_cloudfront`
# resource. The new budget_media module also creates an `aws_s3_bucket_policy.this`
# for the same purpose. If the old resource's address is
# `aws_s3_bucket_policy.budget_media_cloudfront`, move it explicitly:
moved {
  from = aws_s3_bucket_policy.budget_media_cloudfront
  to   = module.budget_media.aws_s3_bucket_policy.this
}

# === CloudFront (was in cloudfront.tf) ===
moved {
  from = aws_cloudfront_origin_access_control.session_videos
  to   = module.cloudfront.aws_cloudfront_origin_access_control.this
}

moved {
  from = aws_cloudfront_distribution.session_videos
  to   = module.cloudfront.aws_cloudfront_distribution.this
}

moved {
  from = aws_s3_bucket_policy.session_videos_cloudfront
  to   = module.cloudfront.aws_s3_bucket_policy.session_videos
}

# === Video thumbnail lambda (was in videos.tf) ===
moved {
  from = aws_iam_role.video_thumbnail_lambda
  to   = module.video_thumbnail_lambda.aws_iam_role.this
}

moved {
  from = aws_iam_role_policy.video_thumbnail_lambda
  to   = module.video_thumbnail_lambda.aws_iam_role_policy.this
}

moved {
  from = aws_lambda_layer_version.ffmpeg
  to   = module.video_thumbnail_lambda.aws_lambda_layer_version.ffmpeg
}

moved {
  from = aws_lambda_function.video_thumbnail
  to   = module.video_thumbnail_lambda.aws_lambda_function.this
}

moved {
  from = aws_lambda_permission.s3_invoke
  to   = module.video_thumbnail_lambda.aws_lambda_permission.s3_invoke
}

moved {
  from = aws_s3_bucket_notification.session_videos
  to   = module.video_thumbnail_lambda.aws_s3_bucket_notification.session_videos
}
