variable "distribution_name" {
  type        = string
  description = "Logical name for the distribution (used for the OAC resource name)."
}

variable "session_videos_bucket_id" {
  type        = string
  description = "Bucket ID (name) of the session videos S3 bucket."
}

variable "session_videos_bucket_arn" {
  type        = string
  description = "Bucket ARN of the session videos S3 bucket."
}

variable "session_videos_bucket_regional_domain_name" {
  type        = string
  description = "Regional domain name of the session videos S3 bucket."
}

variable "session_videos_origin_id" {
  type        = string
  description = "Origin ID for the session videos bucket (e.g. \"powerlifting-session-videos\")."
}

variable "budget_media_bucket_regional_domain_name" {
  type        = string
  description = "Regional domain name of the budget media S3 bucket."
}

variable "budget_media_origin_id" {
  type        = string
  description = "Origin ID for the budget media bucket (e.g. \"powerlifting-budget-media\")."
}
