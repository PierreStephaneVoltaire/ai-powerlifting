resource "aws_dynamodb_table" "workout_videos" {
  name         = "workout-Videos"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "athlete_id"
  range_key    = "video_id"

  attribute {
    name = "athlete_id"
    type = "S"
  }

  attribute {
    name = "video_id"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Terraform   = "true"
    Environment = "dev"
    Name        = "workout"
  }
}
