resource "aws_dynamodb_table" "if_powerlifting_analysis_cache" {
  name         = "if-powerlifting-analysis-cache"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  ttl {
    attribute_name = "expires_at"
    enabled        = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-analysis-cache"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_master_competitions" {
  name             = "if-powerlifting-master-competitions"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-competitions"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_user_competitions" {
  name         = "if-powerlifting-user-competitions"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-user-competitions"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_master_federations" {
  name             = "if-powerlifting-master-federations"
  billing_mode     = "PAY_PER_REQUEST"
  hash_key         = "pk"
  stream_enabled   = true
  stream_view_type = "NEW_AND_OLD_IMAGES"

  attribute {
    name = "pk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-master-federations"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_user_federations" {
  name         = "if-powerlifting-user-federations"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-user-federations"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_goals" {
  name         = "if-powerlifting-goals"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "pk"
  range_key    = "sk"

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-goals"
  }
}
