# ---------------------------------------------------------------------------
# Phase 3 — Lambda functions for the 76 health tools.
#
# Source of truth: each tool folder ships its OWN resources.yaml at
# lambda/<tool>/resources.yaml (layers, memory, timeout, optional s3_read).
# This file discovers them via fileset and generates one aws_lambda_function per
# tool via for_each. Adding a tool = create lambda/<tool>/resources.yaml; no TF
# edit needed.
#
# Each function's source is its self-contained lambda/<tool>/ folder, zipped with
# data.archive_file. Handler = handler.handler, runtime = python3.12, timeout = 900.
# All functions share aws_iam_role.lambda_exec.
# ---------------------------------------------------------------------------

locals {
  # Each tool folder ships its OWN resources.yaml at
  #   lambda/<tool>/resources.yaml
  # (layers, memory, timeout, optional s3_read). fileset finds them all; the tool
  # name is the single directory segment (dirname of "kg_to_lb/resources.yaml").
  # Adding a tool = create lambda/<tool>/resources.yaml; no Terraform edit needed.
  tool_resource_paths = fileset("${path.module}/../lambda", "*/resources.yaml")

  # Decode each folder's own resources.yaml once: tool_name -> raw config object.
  # Each object has keys: layers (list of layer keys), memory (number),
  # timeout (number), s3_read (bool, optional).
  lambda_tool_configs = {
    for rel_path in local.tool_resource_paths :
    dirname(rel_path) => yamldecode(file("${path.module}/../lambda/${rel_path}"))
  }

  # Build the for_each map: tool_name -> merged config object.
  # Normalize missing optional fields (s3_read defaults to false) and resolve
  # each layer key to its ARN via the local layer_arns map (defined in layers.tf).
  lambda_function_configs = {
    for name, cfg in local.lambda_tool_configs : name => {
      layers     = cfg.layers
      memory     = cfg.memory
      timeout    = cfg.timeout
      s3_read    = lookup(cfg, "s3_read", false)
      layer_arns = [for key in cfg.layers : local.layer_arns[key]]
    }
  }

  # Shared env vars every health lambda gets (table names + region + sandbox path).
  # The handlers' config.py reads these via os.getenv; they match the defaults in
  # each lambda/<tool>/config.py but are pinned here so prod never accidentally
  # falls back to the "operator" dev PK.
  lambda_common_env = {
    AWS_REGION                = var.region
    SANDBOX_PATH              = "/tmp/sandbox"
    IF_HEALTH_TABLE_NAME      = var.dynamodb_health_table
    IF_TEMPLATES_TABLE_NAME   = var.dynamodb_templates_table
    IF_SESSIONS_TABLE_NAME    = var.dynamodb_sessions_table
    IF_PROPOSALS_TABLE_NAME   = var.dynamodb_proposals_table
    ANALYSIS_CACHE_TABLE_NAME = var.dynamodb_analysis_cache_table
    HEALTH_PROGRAM_PK         = "operator"
  }

  # Stats lambdas (Stream B) also get the S3 dataset bucket name.
  lambda_stats_env = {
    POWERLIFTING_S3_BUCKET = var.powerlifting_s3_bucket
  }
}

# ---------------------------------------------------------------------------
# Zip each tool's self-contained source folder. Matches the pattern used by
# the existing video-thumbnail Lambda (data.archive_file in videos.tf).
# ---------------------------------------------------------------------------
data "archive_file" "lambda_tool" {
  for_each    = local.lambda_function_configs
  type        = "zip"
  output_path = "${path.module}/build/${each.key}.zip"
  source_dir  = "${path.module}/../lambda/${each.key}"
}

# ---------------------------------------------------------------------------
# One aws_lambda_function per tool. for_each over the config map so the
# function_name, memory, layers, and env vars all come from the per-folder
# resources.yaml. Shared aws_iam_role.lambda_exec (iam.tf).
# ---------------------------------------------------------------------------
resource "aws_lambda_function" "health_tool" {
  for_each = local.lambda_function_configs

  function_name = "${var.lambda_function_prefix}${each.key}"
  role          = aws_iam_role.lambda_exec.arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  memory_size   = each.value.memory
  timeout       = each.value.timeout

  filename         = data.archive_file.lambda_tool[each.key].output_path
  source_code_hash = data.archive_file.lambda_tool[each.key].output_base64sha256

  # Attach the layers resolved from the per-folder resources.yaml (empty list for pure-math).
  layers = each.value.layer_arns

  environment {
    variables = merge(
      local.lambda_common_env,
      # Stats lambdas get the S3 bucket env var; others don't.
      each.value.s3_read ? local.lambda_stats_env : {},
    )
  }

  tags = {
    Project = "powerlifting-app"
    Service = "health-lambda"
    Tool    = each.key
  }

  depends_on = [aws_iam_role_policy.lambda_exec]
}

# ---------------------------------------------------------------------------
# Optional provisioned concurrency for the stats lambdas (Stream B) to cut
# cold-start. Off by default (var.stats_provisioned_concurrency = 0). When > 0,
# an aws_lambda_provisioned_concurrency_config is attached to each stats fn.
# TODO: enable once warm-start strategy is validated (see plan Phase 1 Stream B).
# ---------------------------------------------------------------------------
resource "aws_lambda_provisioned_concurrency_config" "stats" {
  for_each = {
    for name, cfg in local.lambda_function_configs : name => cfg if cfg.s3_read
  }

  function_name                     = aws_lambda_function.health_tool[each.key].function_name
  provisioned_concurrent_executions = var.stats_provisioned_concurrency
  qualifier                         = "$LATEST"
}
