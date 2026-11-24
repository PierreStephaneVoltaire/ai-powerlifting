variable "workload_identity_jwks" {
  type = string
  validation {
    condition     = try(length(jsondecode(var.workload_identity_jwks).keys) > 0 && alltrue([for key in jsondecode(var.workload_identity_jwks).keys : key.kty == "RSA" && can(key.n) && can(key.e) && length(setintersection(toset(keys(key)), toset(["d", "p", "q", "dp", "dq", "qi", "oth"]))) == 0]), false)
    error_message = "workload_identity_jwks must contain only public RSA keys."
  }
}

variable "workload_identity_namespace" {
  type    = string
  default = "powerlifting"
}

data "aws_caller_identity" "workload_identity" {}

locals {
  workload_identity_bucket = "powerlifting-workload-identity-${data.aws_caller_identity.workload_identity.account_id}-ca-central-1"
  workload_identity_host   = "${local.workload_identity_bucket}.s3.ca-central-1.amazonaws.com"
  workload_identity_url    = "https://${local.workload_identity_host}"
  workload_identity_tables = {
    "pl-analytics"     = ["if-health", "if-supplements", "if-sessions", "if-powerlifting-user-competitions", "if-powerlifting-goals", var.glossary_table_name]
    "pl-profile"       = ["if-user", "if-powerlifting-requests", "if-powerlifting-notifications", "if-powerlifting-tags", "if-health", "if-sessions", "if-powerlifting-user-competitions", "workout-Videos"]
    "pl-program"       = ["if-health", "if-sessions", "if-supplements", "if-powerlifting-user-competitions", "if-health-templates"]
    "pl-sessions"      = ["if-health", "if-sessions"]
    "pl-competition"   = ["if-health", "if-sessions", "if-powerlifting-user-competitions", var.glossary_table_name]
    "pl-glossary"      = [var.glossary_table_name, "if-health", "if-sessions"]
    "pl-federation"    = ["if-health", "if-powerlifting-master-federations"]
    "pl-goals"         = ["if-powerlifting-goals"]
    "pl-performance"   = ["if-health", "if-powerlifting-user-competitions"]
    "pl-weight-log"    = ["if-health"]
    "pl-export"        = ["if-health", "if-sessions", "if-supplements", "if-powerlifting-user-competitions", var.glossary_table_name]
    "pl-imports"       = ["if-health", "if-health-templates", "if-supplements", var.glossary_table_name]
    "pl-lift-profiles" = ["if-health", "if-supplements"]
    "pl-templates"     = ["if-health-templates", "if-health", "if-supplements", var.glossary_table_name]
    "pl-videos"        = ["if-health", "if-sessions", "workout-Videos", "if-powerlifting-notifications"]
    "pl-coach-discord" = ["if-user", "if-webhooks"]
  }
  workload_identity_s3 = {
    "powerlifting-app-backend" = ["powerlifting-session-videos"]
    "pl-profile"               = ["powerlifting-session-videos"]
    "pl-videos"                = ["powerlifting-session-videos"]
    "pl-analytics"             = ["powerlifting-data-2b0f699b"]
    "pl-analytics-ai"          = ["powerlifting-data-2b0f699b"]
    "pl-analytics-export"      = ["powerlifting-data-2b0f699b"]
    "pl-rankings"              = ["powerlifting-data-2b0f699b"]
    "pl-coach"                 = ["powerlifting-data-2b0f699b"]
  }
  workload_identity_dynamo_actions = {
    "pl-analytics"     = ["GetItem", "Query"]
    "pl-profile"       = ["GetItem", "PutItem", "UpdateItem", "DeleteItem", "Query", "Scan", "ConditionCheckItem"]
    "pl-program"       = ["GetItem", "PutItem", "Query", "BatchWriteItem"]
    "pl-sessions"      = ["GetItem", "PutItem", "DeleteItem", "Query", "BatchWriteItem"]
    "pl-competition"   = ["GetItem", "UpdateItem", "Query"]
    "pl-glossary"      = ["GetItem", "PutItem", "UpdateItem", "Query"]
    "pl-federation"    = ["GetItem", "PutItem", "Scan", "UpdateItem"]
    "pl-goals"         = ["Query", "PutItem", "DeleteItem"]
    "pl-performance"   = ["GetItem", "PutItem", "Query"]
    "pl-weight-log"    = ["GetItem", "PutItem"]
    "pl-export"        = ["GetItem", "PutItem", "Query", "Scan"]
    "pl-imports"       = ["GetItem", "PutItem", "UpdateItem", "Query", "Scan"]
    "pl-lift-profiles" = ["GetItem", "PutItem", "UpdateItem", "Query", "Scan", "ConditionCheckItem"]
    "pl-templates"     = ["GetItem", "PutItem", "UpdateItem", "DeleteItem", "Query", "Scan", "ConditionCheckItem"]
    "pl-videos"        = ["GetItem", "PutItem", "UpdateItem", "Query", "DeleteItem", "BatchWriteItem"]
    "pl-coach-discord" = ["GetItem", "PutItem", "UpdateItem", "Query"]
  }
  workload_identity_s3_actions = {
    "powerlifting-app-backend" = ["PutObject", "AbortMultipartUpload", "ListMultipartUploadParts"]
    "pl-profile"               = ["PutObject", "DeleteObject"]
    "pl-videos"                = ["GetObject"]
    "pl-analytics"             = ["GetObject", "PutObject"]
    "pl-analytics-ai"          = ["GetObject", "PutObject"]
    "pl-analytics-export"      = ["GetObject", "PutObject"]
    "pl-rankings"              = ["GetObject", "PutObject"]
    "pl-coach"                 = ["GetObject"]
  }
  workload_identity_s3_prefixes = {
    "powerlifting-app-backend" = "videos/*"
    "pl-profile"               = "profiles/*"
    "pl-videos"                = "videos/*"
    "pl-analytics"             = "analysis/*"
    "pl-analytics-ai"          = "analysis-reports/*"
    "pl-analytics-export"      = "lifetime/*"
    "pl-rankings"              = "datasets/openpowerlifting-*"
    "pl-coach"                 = "lifetime/*/latest.md"
  }
  workload_identity_list_prefixes = {
    "pl-analytics"        = "analysis/*"
    "pl-rankings"         = "datasets/openpowerlifting-*"
    "pl-analytics-ai"     = "analysis-reports/*"
    "pl-analytics-export" = "lifetime/*"
    "pl-coach"            = "lifetime/*/latest.md"
  }
  workload_identity_accounts = toset(concat(keys(local.workload_identity_tables), keys(local.workload_identity_s3), ["pl-assistant", "ecr-refresher"]))
}

resource "aws_s3_bucket" "workload_identity" {

  bucket = local.workload_identity_bucket
  lifecycle {
    prevent_destroy = true
    precondition {
      condition     = var.region == "ca-central-1" && var.workload_identity_jwks != ""
      error_message = "Workload identity requires ca-central-1 and the public JWKS."
    }
  }
}

resource "aws_s3_bucket_public_access_block" "workload_identity" {
  lifecycle {
    prevent_destroy = true
  }

  bucket                  = aws_s3_bucket.workload_identity.id
  block_public_acls       = true
  ignore_public_acls      = true
  block_public_policy     = false
  restrict_public_buckets = false
}

resource "aws_s3_bucket_policy" "workload_identity" {
  lifecycle {
    prevent_destroy = true
  }

  bucket = aws_s3_bucket.workload_identity.id
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow", Principal = "*", Action = "s3:GetObject"
      Resource = ["${aws_s3_bucket.workload_identity.arn}/.well-known/openid-configuration", "${aws_s3_bucket.workload_identity.arn}/openid/v1/jwks"]
    }]
  })
  depends_on = [aws_s3_bucket_public_access_block.workload_identity]
}

resource "aws_s3_object" "workload_identity_discovery" {
  lifecycle {
    prevent_destroy = true
  }

  bucket       = aws_s3_bucket.workload_identity.id
  key          = ".well-known/openid-configuration"
  content_type = "application/json"
  content = jsonencode({
    issuer                   = local.workload_identity_url, jwks_uri = "${local.workload_identity_url}/openid/v1/jwks"
    response_types_supported = ["id_token"], subject_types_supported = ["public"], id_token_signing_alg_values_supported = ["RS256"]
  })
}

resource "aws_s3_object" "workload_identity_jwks" {
  lifecycle {
    prevent_destroy = true
  }

  bucket       = aws_s3_bucket.workload_identity.id
  key          = "openid/v1/jwks"
  content_type = "application/json"
  content      = var.workload_identity_jwks
}

resource "aws_iam_openid_connect_provider" "workload_identity" {
  lifecycle {
    prevent_destroy = true
  }

  url            = local.workload_identity_url
  client_id_list = ["sts.amazonaws.com"]
  depends_on     = [aws_s3_bucket_policy.workload_identity, aws_s3_object.workload_identity_discovery, aws_s3_object.workload_identity_jwks]
}

resource "aws_iam_role" "workload_identity" {
  lifecycle {
    prevent_destroy = true
  }
  for_each = local.workload_identity_accounts
  name     = "nolift-${each.key}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow", Action = "sts:AssumeRoleWithWebIdentity"
      Principal = { Federated = aws_iam_openid_connect_provider.workload_identity.arn }
      Condition = { StringEquals = {
        "${local.workload_identity_host}:aud" = "sts.amazonaws.com"
        "${local.workload_identity_host}:sub" = "system:serviceaccount:${var.workload_identity_namespace}:${each.key}"
      } }
    }]
  })
}

resource "aws_iam_role_policy" "workload_identity" {
  lifecycle {
    prevent_destroy = true
  }
  for_each = aws_iam_role.workload_identity
  name     = "nolift-workload-access"
  role     = each.value.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = concat(
      contains(keys(local.workload_identity_tables), each.key) ? [{
        Effect   = "Allow"
        Action   = [for action in lookup(local.workload_identity_dynamo_actions, each.key, []) : "dynamodb:${action}"]
        Resource = flatten([for table in lookup(local.workload_identity_tables, each.key, []) : ["arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/${table}", "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/${table}/index/*"]])
      }] : [],
      contains(["pl-templates", "pl-imports"], each.key) ? [{
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = ["arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/if-sessions"]
      }] : [],
      flatten([for enabled in(contains(["pl-export", "pl-imports", "pl-lift-profiles", "pl-templates", "pl-videos"], each.key) ? [true] : []) : [{
        Effect   = "Allow"
        Action   = ["dynamodb:GetItem", "dynamodb:Scan"]
        Resource = ["arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/if-user"]
        }, {
        Effect   = "Allow"
        Action   = ["dynamodb:Query"]
        Resource = ["arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/if-powerlifting-requests", "arn:aws:dynamodb:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:table/if-powerlifting-user-competitions"]
      }]]),
      contains(keys(local.workload_identity_list_prefixes), each.key) ? [{
        Effect    = "Allow", Action = ["s3:ListBucket"]
        Resource  = [for bucket in lookup(local.workload_identity_s3, each.key, []) : "arn:aws:s3:::${bucket}"]
        Condition = { StringLike = { "s3:prefix" = lookup(local.workload_identity_list_prefixes, each.key, "") } }
      }] : [],
      contains(keys(local.workload_identity_s3), each.key) ? [{
        Effect   = "Allow", Action = [for action in lookup(local.workload_identity_s3_actions, each.key, []) : "s3:${action}"]
        Resource = [for bucket in lookup(local.workload_identity_s3, each.key, []) : "arn:aws:s3:::${bucket}/${lookup(local.workload_identity_s3_prefixes, each.key, "")}"]
      }] : [],
      each.key == "powerlifting-app-backend" ? [{
        Effect = "Allow", Action = "s3:GetObject", Resource = "arn:aws:s3:::powerlifting-session-videos/*"
      }] : [],
      flatten([for enabled in(each.key == "pl-assistant" ? [true] : []) : [{
        Effect    = "Allow", Action = "s3:ListBucketVersions", Resource = aws_s3_bucket.reference_documents.arn
        Condition = { StringLike = { "s3:prefix" = local.reference_prefixes } }
        }, {
        Effect   = "Allow", Action = "s3:GetObjectVersion"
        Resource = [for prefix in local.reference_prefixes : "${aws_s3_bucket.reference_documents.arn}/${prefix}"]
      }]]),
      flatten([for enabled in(each.key == "ecr-refresher" ? [true] : []) : [{
        Effect = "Allow", Action = "ecr:GetAuthorizationToken", Resource = "*"
        }, {
        Effect   = "Allow", Action = ["ecr:BatchCheckLayerAvailability", "ecr:BatchGetImage", "ecr:GetDownloadUrlForLayer"]
        Resource = "arn:aws:ecr:${var.region}:${data.aws_caller_identity.workload_identity.account_id}:repository/if-powerlifting-*"
      }]])
    )
  })
}

output "workload_identity_issuer" {
  value = local.workload_identity_url
}

output "workload_identity_role_arns" {
  value = { for account, role in aws_iam_role.workload_identity : account => role.arn }
}
