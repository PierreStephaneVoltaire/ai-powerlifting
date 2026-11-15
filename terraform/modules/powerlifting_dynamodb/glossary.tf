resource "aws_dynamodb_table" "glossary" {
  name                        = var.glossary_table_name
  billing_mode                = "PAY_PER_REQUEST"
  hash_key                    = "pk"
  range_key                   = "sk"
  stream_enabled              = true
  stream_view_type            = "NEW_IMAGE"
  deletion_protection_enabled = true

  attribute {
    name = "pk"
    type = "S"
  }

  attribute {
    name = "sk"
    type = "S"
  }

  attribute {
    name = "generic_pending"
    type = "S"
  }

  attribute {
    name = "created_at"
    type = "S"
  }

  global_secondary_index {
    name            = "generic-pending"
    hash_key        = "generic_pending"
    range_key       = "created_at"
    projection_type = "ALL"
  }

  point_in_time_recovery {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }

  tags = {
    Project = "if-prototype-a1"
    Service = "powerlifting-glossary"
  }
}
