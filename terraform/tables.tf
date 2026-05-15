resource "aws_dynamodb_table" "if_sessions" {
  name         = var.dynamodb_sessions_table
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
    Service = "sessions"
  }
}

resource "aws_dynamodb_table" "if_powerlifting_analysis_cache" {
  name         = var.dynamodb_analysis_cache_table
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

resource "aws_dynamodb_table" "if_user" {
  name         = var.dynamodb_user_table
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "mapped_pk"

  attribute {
    name = "mapped_pk"
    type = "S"
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "user"
  }
}

resource "aws_dynamodb_table" "if_finance" {
  name         = var.dynamodb_finance_table
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
    Service = "finance"
  }
}

resource "aws_dynamodb_table" "if_diary_entries" {
  name         = var.dynamodb_diary_entries_table
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
    Service = "diary"
  }
}

resource "aws_dynamodb_table" "if_diary_signals" {
  name         = var.dynamodb_diary_signals_table
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
    Service = "diary-signals"
  }
}

resource "aws_dynamodb_table" "if_proposals" {
  name         = var.dynamodb_proposals_table
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
    Service = "proposals"
  }
}
resource "aws_dynamodb_table" "if_models" {
  name         = var.dynamodb_models_table
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
    Service = "model-registry"
  }
}

resource "aws_dynamodb_table" "if_core" {
  name         = var.dynamodb_core_table
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
    Service = "core-directives"
  }
}

resource "aws_dynamodb_table" "if_health" {
  name         = var.dynamodb_health_table
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
    attribute_name = "ttl"
    enabled        = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "health"
  }
}
